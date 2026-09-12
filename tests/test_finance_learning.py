"""Finance Learning Lab tests: curriculum sequencing respects
prerequisites and never lets a weekday-rotation match skip ahead of
untaught foundational topics; spaced repetition schedules a review;
weekly review triggers when the curriculum reaches an is_review topic."""
from __future__ import annotations

from datetime import date, timedelta

from src.analysis.finance_learning import (
    due_for_review,
    generate_finance_lesson,
    generate_weekly_review,
    record_topic_taught,
    select_next_topic,
)
from src.models.database import FinanceLearningProgressRow, get_session
from src.providers.mock_providers import MockLLMProvider


def test_first_topic_is_first_in_curriculum_order(settings, tmp_db):
    """Regression test: an earlier version let a later topic matching
    today's weekday rotation category jump the queue (e.g. picking
    "hedge_funds_intro" over "tvm" on a Saturday). The very first topic
    selected must always be the first one defined in the curriculum,
    regardless of what day of the week it is."""
    topic = select_next_topic(settings, date(2026, 9, 12))  # a Saturday
    assert topic is not None
    assert topic["id"] == settings.finance_topics[0]["id"] == "tvm"


def test_topic_with_unmet_prerequisites_is_skipped(settings, tmp_db):
    """expected_return requires tvm first - if tvm hasn't been taught yet,
    selection must not jump straight to expected_return even though it
    comes third in the list (fs_overview, with no prerequisites, comes
    before it and should be picked once tvm is done)."""
    record_topic_taught(settings, date(2026, 9, 1), settings.finance_topics[0])  # tvm
    topic = select_next_topic(settings, date(2026, 9, 2))
    assert topic["id"] != "expected_return"  # fs_overview (no prereqs) should come first
    assert topic["id"] == "fs_overview"


def test_sequential_progression_across_several_days(settings, tmp_db):
    """Teach topics one at a time across consecutive days and confirm the
    curriculum advances strictly in order (Part 26's fixed Week 1 sequence)."""
    expected_order = ["tvm", "fs_overview", "expected_return", "rates_yields", "options_basics", "hedge_funds_intro"]
    current_date = date(2026, 9, 1)
    for expected_id in expected_order:
        topic = select_next_topic(settings, current_date)
        assert topic["id"] == expected_id, f"expected {expected_id}, got {topic['id']} on {current_date}"
        record_topic_taught(settings, current_date, topic)
        current_date += timedelta(days=1)

    # After all 6 Week-1 lessons, the next selectable item is the review gate.
    topic = select_next_topic(settings, current_date)
    assert topic["id"] == "week1_review"
    assert topic.get("is_review") is True


def test_spaced_repetition_schedules_a_future_review(settings, tmp_db):
    topic = settings.finance_topics[0]
    run_date = date(2026, 9, 1)
    record_topic_taught(settings, run_date, topic)

    from sqlalchemy import select as sa_select

    with get_session() as session:
        row = session.execute(
            sa_select(FinanceLearningProgressRow).where(FinanceLearningProgressRow.topic_id == topic["id"])
        ).scalar_one()
        assert row.next_review_date == run_date + timedelta(days=3)  # first interval in config

    # Not due yet the next day.
    assert due_for_review(settings, run_date + timedelta(days=1)) is None
    # Due once we reach the scheduled review date.
    due = due_for_review(settings, run_date + timedelta(days=3))
    assert due is not None
    assert due.topic_id == topic["id"]


def test_mock_lesson_generation_end_to_end(settings, tmp_db):
    """Full generate_finance_lesson() call using the deterministic mock LLM
    - confirms the flagship tvm content renders through the real schema
    validation path (Pydantic), not just the raw dict."""
    llm = MockLLMProvider()
    lesson = generate_finance_lesson(llm, settings, date(2026, 9, 1))
    assert lesson is not None
    assert lesson.topic_id == "tvm"
    assert lesson.track.value == "CFA_FOUNDATION"
    assert len(lesson.key_takeaways) <= 3
    assert len(lesson.quiz) <= 3
    assert "折现" in lesson.core_concept or "discount" in lesson.core_concept.lower()


def test_weekly_review_triggers_once_week_is_complete(settings, tmp_db):
    llm = MockLLMProvider()
    run_date = date(2026, 9, 1)
    for topic in settings.finance_topics[:6]:  # the 6 real Week-1 lessons
        record_topic_taught(settings, run_date, topic)
        run_date += timedelta(days=1)

    review = generate_weekly_review(llm, settings, run_date)
    assert review is not None
    assert review.week_label == "第一周复习"
    assert len(review.topics_covered) == 6


def test_disabled_module_returns_none(settings, tmp_db):
    settings.finance_curriculum_raw["finance_learning"]["enabled"] = False
    llm = MockLLMProvider()
    lesson = generate_finance_lesson(llm, settings, date(2026, 9, 1))
    assert lesson is None
    settings.finance_curriculum_raw["finance_learning"]["enabled"] = True  # restore for other tests
