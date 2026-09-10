"""Educational content generation + learning memory (Section 19-21;
V2 Part 20-23: structured 5-part lesson + shorter reminders for concepts
already taught many times)."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from sqlalchemy import select

from src.models.database import LearningConceptRow, get_session
from src.models.schemas import EducationalContent, MarketRegimeView, StoryAnalysis
from src.providers.llm_base import LLMProvider
from src.analysis.llm_client import call_llm_json

TASK = "educational_content"

INSTRUCTIONS = """Using INPUT_DATA.regime_summary and INPUT_DATA.top_stories as the real market \
context, produce:

1. learn_one_thing: ONE concept directly tied to today's actual market action (see \
INPUT_DATA.recently_taught_concepts - avoid re-teaching a concept taught in the last \
INPUT_DATA.recap_window_days days unless it's unusually important again; prefer progressing to a \
new or slightly more advanced concept - INPUT_DATA.concept_mastery gives times_explained per \
concept so you can gauge what the reader likely already knows). Structure it as 5 parts \
(Part 20 of the V2 spec):
   - question: "今天的问题" - a specific question today's market raises for a junior trader
   - core_concept: the professional concept that answers it, explained in plain Chinese
   - todays_example: how this showed up in TODAY's actual data/news (not a generic example)
   - common_mistake: (optional but preferred) a common beginner misreading of this situation
   - trader_takeaway: one crisp, actionable mental habit to carry forward
Combined length should be roughly 300-600 Chinese characters (well over the 150-character minimum).

2. terminology: 1-5 potentially-unfamiliar terms that appear in today's analysis (e.g. terms like \
"backlog", "ASP", "gross margin", "basis point", "bid-to-cover", "HBM", "operating leverage", \
"priced in", "earnings revision", "relative strength"). For each: plain-language definition, why \
traders care, and a concrete example tied to today's data if possible. If INPUT_DATA.concept_mastery \
shows a term has been explained 5+ times already, either omit it or keep the explanation to one \
short clause instead of a full definition (Part 22: don't re-teach VIX from scratch every day).

Return JSON:
{
  "learn_one_thing": {
    "title": "short label for this lesson",
    "question": "...",
    "core_concept": "...",
    "todays_example": "...",
    "common_mistake": "..." or null,
    "trader_takeaway": "...",
    "tied_to_event": "..." or null
  },
  "terminology": [{"term": "...", "plain_definition": "...", "why_traders_care": "...", "todays_example": "..." }, ...]
}"""

# Fallback used only if the LLM call fails validation - keeps the report
# non-empty rather than silently dropping the educational section.
FALLBACK_LEARN_ONE_THING = {
    "title": "为什么同一条新闻，对不同股票的意义可能完全不同",
    "question": "今天有好消息，为什么股价不一定会涨？",
    "core_concept": (
        "作为交易者，最值得养成的习惯之一，不是简单地问'这条新闻是好是坏'，而是问'对谁是好、对谁是坏，"
        "以及这件事市场是不是已经预期到了'。专业投资者习惯把一条新闻沿着链条去追问：谁最先受益"
        "（一级影响，first-order），谁接下来受益（二级影响，second-order），谁可能被挤压。他们还会问："
        "这件事此前是不是已经被市场'定价'（priced in）了。"
    ),
    "todays_example": (
        "今天的分析引擎暂时不可用，无法生成与当日行情直接挂钩的具体例子——但这个框架本身在任何一天都适用："
        "看到一条消息时，先问它是否已经被市场预期到，再判断股价反应是否合理。"
    ),
    "common_mistake": "'利好新闻 = 应该买入'——这个推理忽略了这条消息是否已经反映在价格里。",
    "trader_takeaway": (
        "养成把 FACT（发生了什么）、INTERPRETATION（这可能意味着什么）、"
        "以及是否已经 PRICED IN（市场是否已预期）分开看的习惯，比记住任何单一指标都更有长期价值。"
    ),
    "tied_to_event": None,
}


def get_recently_taught_concepts(run_date: date, window_days: int = 21) -> List[str]:
    from datetime import timedelta

    cutoff = run_date - timedelta(days=window_days)
    with get_session() as session:
        rows = session.execute(
            select(LearningConceptRow).where(LearningConceptRow.last_explained >= cutoff)
        ).scalars().all()
        return [r.concept for r in rows]


def get_concept_mastery(run_date: date) -> Dict[str, int]:
    """concept -> times_explained, used so the analysis engine can shorten
    or skip re-explaining a term it has already taught many times (Part 22)."""
    with get_session() as session:
        rows = session.execute(select(LearningConceptRow)).scalars().all()
        return {r.concept: r.times_explained for r in rows}


def record_concepts_taught(run_date: date, concepts: List[str], user_level: str = "beginner") -> None:
    with get_session() as session:
        for concept in concepts:
            existing = session.execute(
                select(LearningConceptRow).where(LearningConceptRow.concept == concept)
            ).scalar_one_or_none()
            if existing:
                existing.times_explained += 1
                existing.last_explained = run_date
            else:
                session.add(
                    LearningConceptRow(
                        concept=concept,
                        first_seen=run_date,
                        times_explained=1,
                        last_explained=run_date,
                        user_level=user_level,
                    )
                )


def generate_educational_content(
    llm: LLMProvider,
    regime: MarketRegimeView,
    top_stories: List[StoryAnalysis],
    run_date: date,
    recap_window_days: int = 21,
    max_terms: int = 5,
) -> EducationalContent:
    recently_taught = get_recently_taught_concepts(run_date, recap_window_days)
    concept_mastery = get_concept_mastery(run_date)
    input_data: Dict[str, Any] = {
        "regime_summary": regime.summary,
        "regime_labels": [l.value for l in regime.labels],
        "top_stories": [
            {"title": s.title, "why_it_matters": s.why_it_matters, "fact": s.fact}
            for s in top_stories[:5]
        ],
        "recently_taught_concepts": recently_taught,
        "concept_mastery": concept_mastery,
        "recap_window_days": recap_window_days,
        "max_terminology_terms": max_terms,
    }
    result = call_llm_json(llm, TASK, INSTRUCTIONS, input_data, EducationalContent)
    if result is not None:
        result.terminology = result.terminology[:max_terms]
        return result

    from src.models.schemas import LearnOneThing

    return EducationalContent(
        learn_one_thing=LearnOneThing(**FALLBACK_LEARN_ONE_THING),
        terminology=[],
    )
