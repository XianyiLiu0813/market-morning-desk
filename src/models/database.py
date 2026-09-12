"""SQLAlchemy models + engine/session helpers (Section 28).

SQLite for V1. Raw data (market snapshots, articles, LLM analysis JSON) is
stored so a report can be regenerated/audited later without re-hitting
external providers.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, date
from typing import Any, Dict, Iterator, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class MarketSnapshotRow(Base):
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    display_name = Column(String)
    group_name = Column(String)
    previous_close = Column(Float, nullable=True)
    last_price = Column(Float, nullable=True)
    daily_pct = Column(Float, nullable=True)
    overnight_pct = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    relative_volume = Column(Float, nullable=True)
    return_5d_pct = Column(Float, nullable=True)
    return_1m_pct = Column(Float, nullable=True)
    pct_from_52w_high = Column(Float, nullable=True)
    as_of = Column(DateTime, nullable=True)
    data_source = Column(String, default="unknown")
    is_stale = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class NewsArticleRow(Base):
    __tablename__ = "news_articles"
    # Uniqueness is scoped to (run_date, article_id), NOT a bare unique
    # article_id: the same real-world article can legitimately still be
    # listed in an RSS feed's most-recent-N-items window across two
    # consecutive daily runs (e.g. published late yesterday, still present
    # when today's run polls "since_hours" back), which reproduces the
    # same deterministic article_id hash. The per-run_date cleanup in
    # pipeline.py only deletes THIS run_date's rows before re-inserting, so
    # a bare global-unique article_id would collide with yesterday's
    # still-present row and crash the whole pipeline with an
    # IntegrityError - this happened in production (see git history).
    __table_args__ = (UniqueConstraint("run_date", "article_id", name="uq_news_articles_run_date_article_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(String, nullable=False, index=True)
    run_date = Column(Date, nullable=False, index=True)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    body_excerpt = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    source_id = Column(String, nullable=True)
    source_name = Column(String, nullable=True)
    tier = Column(Integer, nullable=True)
    published_at = Column(DateTime, nullable=True)
    tickers_json = Column(Text, default="[]")
    themes_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)


class NewsClusterRow(Base):
    __tablename__ = "news_clusters"
    # Same reasoning as NewsArticleRow above: cluster_id is derived from the
    # representative article's id, which can recur across two consecutive
    # daily runs (an RSS feed still listing yesterday's article this
    # morning) - uniqueness must be scoped to (run_date, cluster_id), not
    # global, or the second day's insert crashes with an IntegrityError
    # exactly like the news_articles bug did.
    __table_args__ = (UniqueConstraint("run_date", "cluster_id", name="uq_news_clusters_run_date_cluster_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(String, nullable=False, index=True)
    run_date = Column(Date, nullable=False, index=True)
    title = Column(Text, nullable=False)
    member_article_ids_json = Column(Text, default="[]")
    tickers_json = Column(Text, default="[]")
    themes_json = Column(Text, default="[]")
    importance_json = Column(Text, default="{}")
    total_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class AnalysisResultRow(Base):
    """Generic store for any structured LLM analysis output (story, regime,
    theme, company, trade, learning) keyed by kind + run_date."""

    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)  # regime|story|theme|company|trade|learning|mental_model
    ref_key = Column(String, nullable=True)  # e.g. cluster_id, ticker, theme_key
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ThemeRow(Base):
    __tablename__ = "themes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    theme_key = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)


class ThemeDailyViewRow(Base):
    __tablename__ = "theme_daily_views"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False, index=True)
    theme_key = Column(String, nullable=False, index=True)
    structural_view = Column(String, nullable=False)
    tactical_view = Column(String, nullable=False)
    momentum = Column(String, nullable=False)
    evidence_json = Column(Text, default="[]")
    risk = Column(Text, nullable=True)
    confidence_pct = Column(Integer, default=50)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompanyEventRow(Base):
    __tablename__ = "company_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    company_name = Column(String, nullable=True)
    signal = Column(String, default="NEUTRAL")
    what_changed = Column(Text, nullable=True)
    relevant_driver = Column(String, nullable=True)
    driver_explanation = Column(Text, nullable=True)
    confidence_pct = Column(Integer, default=50)
    created_at = Column(DateTime, default=datetime.utcnow)


class TradeIdeaRow(Base):
    __tablename__ = "trade_ideas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False, index=True)
    ticker = Column(String, nullable=True, index=True)
    direction = Column(String, nullable=False)
    thesis = Column(Text, nullable=True)
    invalidation_condition = Column(Text, nullable=True)
    reference_price = Column(Float, nullable=True)
    confidence_pct = Column(Integer, default=30)
    payload_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class MacroEventRow(Base):
    __tablename__ = "macro_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False, index=True)
    event = Column(String, nullable=False)
    scheduled_at_sgt = Column(DateTime, nullable=True)
    expected = Column(String, nullable=True)
    previous = Column(String, nullable=True)
    actual = Column(String, nullable=True)
    importance = Column(String, default="MEDIUM")
    notes = Column(Text, nullable=True)


class ReportRow(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False, unique=True, index=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    html_path = Column(Text, nullable=True)
    json_payload = Column(Text, nullable=False)
    degraded_mode = Column(Boolean, default=False)
    email_status = Column(String, default="not_sent")  # not_sent|sent|failed|skipped


class LearningConceptRow(Base):
    __tablename__ = "learning_concepts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    concept = Column(String, nullable=False, unique=True, index=True)
    first_seen = Column(Date, nullable=False)
    times_explained = Column(Integer, default=1)
    last_explained = Column(Date, nullable=False)
    user_level = Column(String, default="beginner")  # beginner|intermediate|advanced


class FinanceLearningProgressRow(Base):
    """Finance Learning Lab (new module) - tracks curriculum progress per
    topic_id (defined in config/finance_curriculum.yaml), independent of
    the general learning_concepts table used by the market report's
    'Learn One Thing Today' section. One row per topic_id (upserted, not
    per-run), since this is a long-running curriculum-progress record, not
    a per-day audit log."""

    __tablename__ = "finance_learning_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(String, nullable=False, unique=True, index=True)
    topic_name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    track = Column(String, nullable=False)  # CFA_FOUNDATION | BEYOND_CFA
    difficulty = Column(String, default="foundation")
    first_taught = Column(Date, nullable=True)
    last_taught = Column(Date, nullable=True)
    times_reviewed = Column(Integer, default=0)
    mastery_score = Column(Integer, default=0)  # simple 0-100 heuristic, see finance_learning.py
    next_review_date = Column(Date, nullable=True)
    completed = Column(Boolean, default=False)
    related_topics_json = Column(Text, default="[]")
    # The lesson's one_liner, captured at teach-time, so a later spaced-
    # repetition recap (Part 9's "30-second review") has real content to
    # show rather than a placeholder pointing at nothing.
    review_summary = Column(Text, nullable=True)


class SystemRunRow(Base):
    __tablename__ = "system_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False, unique=True, index=True)
    run_date = Column(Date, nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    providers_used_json = Column(Text, default="{}")
    articles_collected = Column(Integer, default=0)
    stories_after_dedup = Column(Integer, default=0)
    stories_analyzed = Column(Integer, default=0)
    llm_calls = Column(Integer, default=0)
    tokens_used = Column(Integer, nullable=True)
    failures_json = Column(Text, default="[]")
    email_status = Column(String, default="not_sent")
    report_id = Column(Integer, nullable=True)
    status = Column(String, default="running")  # running|success|failed|degraded


class SourceRecordRow(Base):
    __tablename__ = "source_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False, index=True)
    source_id = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    tier = Column(Integer, nullable=False)
    kind = Column(String, default="unknown")
    url = Column(Text, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)


# --------------------------------------------------------------------------
# Engine / session management
# --------------------------------------------------------------------------

_engine = None
_SessionLocal = None


def init_db(db_path: str) -> None:
    global _engine, _SessionLocal
    from pathlib import Path as _Path

    db_file = _Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(f"sqlite:///{db_file}", future=True)
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def get_session() -> Iterator[Any]:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dumps(obj: Any) -> str:
    """JSON-dump helper that tolerates date/datetime/pydantic models."""

    def default(o: Any) -> Any:
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if hasattr(o, "model_dump"):
            return o.model_dump(mode="json")
        return str(o)

    return json.dumps(obj, default=default)
