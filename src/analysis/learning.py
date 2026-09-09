"""Educational content generation + learning memory (Section 19-21)."""
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
INPUT_DATA.recently_taught_concepts - avoid re-teaching a beginner concept taught in the last \
INPUT_DATA.recap_window_days days unless it's unusually important again; prefer progressing to a \
new or slightly more advanced concept). Body should be roughly 300-600 Chinese characters (well \
over the 150-character minimum), written for a learning trader: professional but clearly explained, connect it explicitly \
to today's event(s).

2. terminology: 1-5 potentially-unfamiliar terms that appear in today's analysis (e.g. terms like \
"backlog", "ASP", "gross margin", "basis point", "bid-to-cover", "HBM", "operating leverage", \
"priced in"). For each: plain-language definition, why traders care, and a concrete example tied \
to today's data if possible.

Return JSON:
{
  "learn_one_thing": {"title": "...", "body": "...", "tied_to_event": "..."},
  "terminology": [{"term": "...", "plain_definition": "...", "why_traders_care": "...", "todays_example": "..." }, ...]
}"""

# Fallback library used only if the LLM call fails validation - keeps the
# report non-empty rather than silently dropping the educational section.
FALLBACK_LEARN_ONE_THING = {
    "title": "为什么同一条新闻，对不同股票的意义可能完全不同",
    "body": (
        "作为交易者，最值得养成的习惯之一，不是简单地问'这条新闻是好是坏'，而是问'对谁是好、对谁是坏，"
        "以及这件事市场是不是已经预期到了'。同一条头条新闻——比如一家公司宣布加大支出计划——对它的供应商"
        "可能是利好（供应商可能卖得更多），但对公司自身短期的利润率却可能是中性偏负面的（还没产生收入就先"
        "花钱，会压制自由现金流，free cash flow）。专业投资者习惯把一条新闻沿着链条去追问：谁最先受益"
        "（一级影响，first-order），谁接下来受益（二级影响，second-order），谁可能被挤压。他们还会问："
        "这件事此前是不是已经被市场'定价'（priced in）了——如果一家公司本来就被普遍预期会上调业绩指引，"
        "那它真的上调了，股价可能反应平平，甚至下跌，因为这个'好消息'早就已经反映在价格里了。这也是为什么"
        "专业分析总是把 FACT（发生了什么）、INTERPRETATION（这可能意味着什么）、以及是否已经 PRICED IN"
        "（市场是否已经预期到）这三者分开来看，而不是看到消息就直接下结论。养成这个习惯，比记住任何一个"
        "单一指标都更有长期价值。"
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
    input_data: Dict[str, Any] = {
        "regime_summary": regime.summary,
        "regime_labels": [l.value for l in regime.labels],
        "top_stories": [
            {"title": s.title, "why_it_matters": s.why_it_matters, "fact": s.fact}
            for s in top_stories[:5]
        ],
        "recently_taught_concepts": recently_taught,
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
