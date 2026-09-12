"""Finance Learning Lab (new module).

Appended to the daily report as its own ~1-page section - does NOT modify
any existing market-analysis module. Two parallel tracks (CFA_FOUNDATION,
BEYOND_CFA) drawn from config/finance_curriculum.yaml, with:
  - sequential topic progression respecting prerequisites (never jumps
    ahead of an incomplete prerequisite - Part 7/13),
  - simple spaced repetition (a "30-second review" of a previously-taught
    topic when it comes due - Part 9),
  - a weekly review in place of a new topic when the curriculum reaches a
    topic flagged `is_review: true` (Part 18),
  - real content from an LLM call (task "finance_lesson") when a real
    provider is configured, or a curriculum-metadata-driven mock/fallback
    otherwise.

All persistence is upserted by topic_id (one row per topic forever, not a
per-run audit log) - this is a genuinely different access pattern from the
per-run tables in database.py, so it correctly keeps its bare unique
constraint (see FinanceLearningProgressRow's docstring).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select

from src.analysis.llm_client import call_llm_json
from src.models.database import FinanceLearningProgressRow, get_session
from src.models.schemas import (
    FinanceLesson,
    MarketRegimeView,
    StoryAnalysis,
    WeeklyFinanceReview,
)
from src.providers.llm_base import LLMProvider
from src.utils.config import Settings

TASK = "finance_lesson"
WEEKLY_REVIEW_TASK = "weekly_finance_review"

INSTRUCTIONS = """Write ONE day's "Finance Learning Lab" entry for a junior analyst studying \
finance (both for the CFA exams AND to build a broader real-world professional-investor \
knowledge base - the goal is understanding, not passing a specific exam). Write in Simplified \
Chinese, keeping English financial terminology visible alongside the Chinese explanation (e.g. \
"Duration（久期）", "Tracking Error（跟踪误差）") - never Chinese-only, never English-only.

Style: like a senior analyst explaining something to a junior analyst over coffee - clear logic, \
a concrete numerical or real-world example, professional terminology used correctly, no textbook/ \
Wikipedia tone. Teaching order for the core concept: WHY this concept exists / what problem it \
solves -> intuition in plain language -> (only if a formula is essential) the formula with every \
variable explained -> a simple worked numerical example -> how professionals actually use it. \
Do NOT lead with heavy math for quantitative topics - intuition first, formula second.

INPUT_DATA.topic gives the required topic (name/category/track/difficulty/prerequisites already \
taught/cfa_connection/beyond_cfa_note/where_used - use these as authoritative facts, do not invent \
different ones). INPUT_DATA.today_market_context has today's actual market regime/top stories - \
use it for market_connection ONLY if there's a genuine, non-forced link between the topic and \
today's market (e.g. today's lesson is Duration and 10Y yields moved sharply) - otherwise set \
market_connection to null or use a generic/historical example instead of forcing a connection.

Return JSON:
{
  "one_liner": "the concept in ONE simple sentence",
  "core_concept": "2-4 short paragraphs, professional but clear, no unnecessary jargon",
  "worked_example": "a concrete numerical or real-world example, with the caveat that any \
approximation/simplification is not an exact prediction where relevant",
  "why_investors_care": "why this matters in real investing/trading, per the teaching order above",
  "market_connection": "genuine link to today's market context, or null - never forced",
  "common_mistake": "one concise junior-analyst misconception and its correction, or null",
  "key_takeaways": ["at most 3 short bullet points - the core things to remember"],
  "quiz": [
    {"question": "concept-check question", "answer": "..."},
    {"question": "application question", "answer": "..."},
    {"question": "a slightly harder reasoning question", "answer": "..."}
  ]
}"""

WEEKLY_REVIEW_INSTRUCTIONS = """Produce a weekly Finance Learning Lab review (in Simplified \
Chinese, English terms kept visible) instead of a new lesson. INPUT_DATA.topics_covered lists the \
topics taught this week (id, name). Build a short knowledge CHAIN showing how they connect (e.g. \
"Expected Return -> Variance -> Correlation -> Diversification -> Portfolio Risk"), a 2-4 sentence \
connections_summary tying them together conceptually, and a 5-question quiz spanning the week's \
topics. Keep it to roughly one page total.

Return JSON:
{
  "knowledge_chain": ["Topic A", "Topic B", "..."],
  "connections_summary": "...",
  "quiz": [{"question": "...", "answer": "..."}, ...]  (5 items)
}"""


def _topics_by_id(settings: Settings) -> Dict[str, Dict[str, Any]]:
    return {t["id"]: t for t in settings.finance_topics}


def _get_progress(session, topic_id: str) -> Optional[FinanceLearningProgressRow]:
    return session.execute(
        select(FinanceLearningProgressRow).where(FinanceLearningProgressRow.topic_id == topic_id)
    ).scalar_one_or_none()


def _completed_topic_ids() -> set:
    with get_session() as session:
        rows = session.execute(
            select(FinanceLearningProgressRow).where(FinanceLearningProgressRow.completed.is_(True))
        ).scalars().all()
        return {r.topic_id for r in rows}


def select_next_topic(settings: Settings, run_date: date) -> Optional[Dict[str, Any]]:
    """Part 7/13: walk the curriculum in the order it's defined in
    config/finance_curriculum.yaml, skipping anything already completed or
    whose prerequisites aren't all satisfied yet. Returns the FIRST such
    topic - i.e. strict sequential progression through the curriculum.

    Weekday category_rotation (Part 17) is intentionally NOT applied as an
    override here: an earlier version of this function let a later topic
    that happened to match today's weekday category jump ahead of earlier,
    still-untaught foundational topics (e.g. picking "What Do Hedge Funds
    Actually Do?" over "Time Value of Money" just because it was a
    Saturday) - which directly contradicts the spec's own "learning
    progression is more important than weekday rules" principle (Part 17)
    and the explicit fixed Week 1-4 sequence (Part 26). The rotation
    config is kept in the YAML as documentation for a future, more
    sophisticated scheduler (e.g. once the curriculum has genuinely
    parallel branches at the same prerequisite depth), but selection today
    is deliberately just "next in line"."""
    completed = _completed_topic_ids()
    topics = settings.finance_topics

    for t in topics:
        if t["id"] in completed:
            continue
        if all(p in completed for p in t.get("prerequisites", [])):
            return t
    return None


def due_for_review(settings: Settings, run_date: date) -> Optional[FinanceLearningProgressRow]:
    """Part 9: the single most-overdue previously-taught topic, if any, for
    a 30-second recap prepended to today's lesson."""
    if not settings.finance_learning_config.get("spaced_repetition", True):
        return None
    with get_session() as session:
        rows = session.execute(
            select(FinanceLearningProgressRow)
            .where(FinanceLearningProgressRow.next_review_date.is_not(None))
            .where(FinanceLearningProgressRow.next_review_date <= run_date)
            .order_by(FinanceLearningProgressRow.next_review_date.asc())
        ).scalars().first()
        if rows is None:
            return None
        return FinanceLearningProgressRow(
            topic_id=rows.topic_id, topic_name=rows.topic_name, times_reviewed=rows.times_reviewed,
            review_summary=rows.review_summary,
        )


def _next_review_date(settings: Settings, run_date: date, times_reviewed: int) -> date:
    intervals = settings.finance_learning_config.get("review_intervals_days", [3, 7, 30])
    idx = min(times_reviewed, len(intervals) - 1)
    return run_date + timedelta(days=intervals[idx])


def record_topic_taught(
    settings: Settings, run_date: date, topic: Dict[str, Any], review_summary: Optional[str] = None,
) -> None:
    with get_session() as session:
        existing = _get_progress(session, topic["id"])
        if existing is None:
            session.add(
                FinanceLearningProgressRow(
                    topic_id=topic["id"], topic_name=topic["name_zh"], category=topic.get("category"),
                    track=topic["track"].upper(), difficulty=topic.get("difficulty", "foundation"),
                    first_taught=run_date, last_taught=run_date, times_reviewed=0,
                    next_review_date=_next_review_date(settings, run_date, 0),
                    completed=True, review_summary=review_summary,
                )
            )
        else:
            existing.last_taught = run_date
            existing.completed = True
            if review_summary:
                existing.review_summary = review_summary


def record_topic_reviewed(settings: Settings, run_date: date, topic_id: str) -> None:
    with get_session() as session:
        existing = _get_progress(session, topic_id)
        if existing is None:
            return
        existing.times_reviewed += 1
        existing.last_taught = run_date
        existing.next_review_date = _next_review_date(settings, run_date, existing.times_reviewed)


def progress_label(settings: Settings) -> str:
    total = len(settings.finance_topics)
    completed = len(_completed_topic_ids())
    level = settings.finance_learning_config.get("user_level", "foundation")
    return f"{level.capitalize()} · {completed}/{total} 已学完"


def _build_review_recap(review_row: FinanceLearningProgressRow) -> str:
    summary = review_row.review_summary or f"{review_row.topic_name}（概念回顾内容暂缺）"
    return f"30秒复习 · {review_row.topic_name}：{summary}"


def generate_finance_lesson(
    llm: LLMProvider,
    settings: Settings,
    run_date: date,
    regime: Optional[MarketRegimeView] = None,
    top_stories: Optional[List[StoryAnalysis]] = None,
) -> Optional[FinanceLesson]:
    """Returns None only if the module is disabled or the curriculum is
    fully exhausted (nothing left to teach and no review due) - the
    pipeline should simply omit the section in that case, never crash."""
    if not settings.finance_learning_config.get("enabled", True):
        return None

    topic = select_next_topic(settings, run_date)
    if topic is None:
        return None

    if topic.get("is_review"):
        return None  # handled by generate_weekly_review() instead

    review_row = due_for_review(settings, run_date)
    review_recap_hint = (
        f"{review_row.topic_name}（已学过 {review_row.times_reviewed + 1} 次）" if review_row else None
    )

    market_context = {}
    if regime is not None:
        market_context["regime_labels"] = [l.value for l in regime.labels]
        market_context["regime_summary"] = regime.summary
    if top_stories:
        market_context["top_story_titles"] = [s.title for s in top_stories[:3]]

    input_data = {
        "topic": {
            "id": topic["id"],
            "name_en": topic["name_en"],
            "name_zh": topic["name_zh"],
            "category": topic.get("category"),
            "track": topic["track"],
            "difficulty": topic.get("difficulty", "foundation"),
            "cfa_connection": topic.get("cfa_connection", []),
            "beyond_cfa_note": topic.get("beyond_cfa_note"),
            "where_used": topic.get("where_used", []),
        },
        "today_market_context": market_context,
        "review_due": review_recap_hint,
    }
    result = call_llm_json(llm, TASK, INSTRUCTIONS, input_data, _FinanceLessonBody, max_tokens=2048)
    if result is None:
        return None

    lesson = FinanceLesson(
        topic_id=topic["id"],
        topic_name=topic["name_zh"],
        track=topic["track"].upper(),
        difficulty=topic.get("difficulty", "foundation"),
        progress_label=progress_label(settings),
        review_recap=(_build_review_recap(review_row) if review_row else None),
        one_liner=result.one_liner,
        core_concept=result.core_concept,
        worked_example=result.worked_example,
        why_investors_care=result.why_investors_care,
        market_connection=result.market_connection,
        common_mistake=result.common_mistake,
        key_takeaways=result.key_takeaways,
        quiz=result.quiz,
        cfa_connection=topic.get("cfa_connection", []),
        beyond_cfa_note=topic.get("beyond_cfa_note"),
        where_used=topic.get("where_used", []),
    )

    record_topic_taught(settings, run_date, topic, review_summary=result.one_liner)
    if review_row is not None:
        record_topic_reviewed(settings, run_date, review_row.topic_id)
    return lesson


def generate_weekly_review(llm: LLMProvider, settings: Settings, run_date: date) -> Optional[WeeklyFinanceReview]:
    topic = select_next_topic(settings, run_date)
    if topic is None or not topic.get("is_review"):
        return None

    topics_by_id = _topics_by_id(settings)
    covered = [
        {"id": pid, "name": topics_by_id[pid]["name_zh"]}
        for pid in topic.get("prerequisites", [])
        if pid in topics_by_id
    ]
    input_data = {"topics_covered": covered}
    result = call_llm_json(llm, WEEKLY_REVIEW_TASK, WEEKLY_REVIEW_INSTRUCTIONS, input_data, _WeeklyReviewBody, max_tokens=1536)
    if result is None:
        return None

    review = WeeklyFinanceReview(
        week_label=topic["name_zh"],
        topics_covered=[c["name"] for c in covered],
        knowledge_chain=result.knowledge_chain,
        connections_summary=result.connections_summary,
        quiz=result.quiz,
    )
    record_topic_taught(settings, run_date, topic)
    return review


# Internal wrapper schemas (call_llm_json needs one Pydantic model per
# task; FinanceLesson/WeeklyFinanceReview themselves carry extra fields
# (topic_id, cfa_connection, etc.) that are filled in from curriculum
# metadata afterward, not by the LLM, so the LLM-facing schema is a subset).
class _FinanceLessonBody(BaseModel):
    one_liner: str
    core_concept: str
    worked_example: str
    why_investors_care: str
    market_connection: Optional[str] = None
    common_mistake: Optional[str] = None
    key_takeaways: List[str] = Field(default_factory=list)
    quiz: List[Any] = Field(default_factory=list)


class _WeeklyReviewBody(BaseModel):
    knowledge_chain: List[str] = Field(default_factory=list)
    connections_summary: str
    quiz: List[Any] = Field(default_factory=list)
