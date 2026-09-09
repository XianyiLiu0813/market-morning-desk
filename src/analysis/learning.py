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
    "title": "Why the same news can mean different things to different stocks",
    "body": (
        "One of the most important habits to build as a trader is asking not just 'is this "
        "news good or bad', but 'good or bad for whom, and how much of it is already expected'. "
        "The same headline - say, a company raising its spending plans - can be read as bullish "
        "for its suppliers (they may sell more) and neutral-to-bearish for the company's own "
        "margins in the near term (spending more before it generates revenue can pressure free "
        "cash flow). Professional investors habitually trace a single piece of news along a "
        "chain: who benefits first (first-order), who benefits next (second-order), and who "
        "might be squeezed. They also ask what was already priced into the stock beforehand - "
        "if a company was already expected to raise guidance, actually raising it may cause "
        "little reaction, or even a decline, because the 'good news' was already reflected in "
        "the price. This is why professional analysis always separates FACT (what was "
        "announced), INTERPRETATION (what it might mean), and PRICED-IN status (whether the "
        "market already expected it) before jumping to a trade conclusion. Building this habit "
        "is more valuable long-term than memorizing any single indicator."
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
