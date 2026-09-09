"""End-to-end morning pipeline orchestration.

This module wires together collectors -> processing -> analysis ->
rendering -> persistence -> email, matching the Section 3 pipeline stages
and Section 47 acceptance criteria. `main.py` is a thin CLI wrapper around
`run_morning_pipeline`.
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from src.analysis.company_analysis import analyze_companies
from src.analysis.editor import synthesize_report
from src.analysis.learning import generate_educational_content, record_concepts_taught
from src.analysis.macro_analysis import split_macro_vs_market
from src.analysis.market_regime import infer_market_regime
from src.analysis.story_analysis import analyze_stories
from src.analysis.theme_analysis import analyze_themes
from src.analysis.trade_analysis import generate_trade_ideas
from src.analysis.yesterday_review import build_review, get_prior_trade_ideas
from src.collectors.macro import collect_macro_calendar
from src.collectors.market import collect_market_snapshot
from src.collectors.news import process_news_pipeline
from src.email.sender import send_morning_email
from src.models.database import (
    AnalysisResultRow,
    CompanyEventRow,
    MacroEventRow,
    MarketSnapshotRow,
    NewsArticleRow,
    NewsClusterRow,
    ReportRow,
    SourceRecordRow,
    SystemRunRow,
    ThemeDailyViewRow,
    TradeIdeaRow,
    dumps,
    get_session,
    init_db,
)
from src.models.schemas import MorningReport, SourceRecord, SourceTier
from src.processing.quality import run_quality_checks
from src.processing.scoring import score_clusters
from src.providers.factory import (
    build_email_provider,
    build_llm_provider,
    build_macro_provider,
    build_market_provider,
    build_news_providers,
)
from src.reports.renderer import render_report
from src.utils.config import Settings, get_settings
from src.utils.logging import get_logger, new_run_id
from src.utils.time import now_sgt, now_utc

logger = logging.getLogger("morning_desk")


def run_morning_pipeline(
    run_date: Optional[date] = None,
    settings: Optional[Settings] = None,
    send_email: bool = True,
    output_dir: str = "outbox",
) -> Dict[str, Any]:
    settings = settings or get_settings()
    run_date = run_date or now_sgt().date()
    run_id = new_run_id()
    get_logger()

    init_db(settings.db_path)

    started_at = datetime.utcnow()
    providers_used: Dict[str, str] = {}
    failures: List[str] = []
    llm_calls = 0

    with get_session() as session:
        session.add(SystemRunRow(run_id=run_id, run_date=run_date, started_at=started_at, status="running"))

    logger.info("=== Morning pipeline started (run_id=%s, run_date=%s, mock_mode=%s) ===",
                run_id, run_date, settings.mock_mode)

    # 1. Market data collection
    market_provider = build_market_provider(settings)
    providers_used["market"] = market_provider.name
    snapshot = collect_market_snapshot(market_provider, settings, run_date)
    assets_by_symbol = {a.symbol: a for a in snapshot.assets}
    logger.info("Market snapshot: %d assets collected", len(snapshot.assets))

    # 2. News collection -> normalize -> dedup -> enrich -> cluster
    news_providers = build_news_providers(settings)
    providers_used["news"] = ",".join(p.name for p in news_providers)
    raw_articles, clusters = process_news_pipeline(news_providers, settings, since_hours=18)
    articles_collected = len(raw_articles)

    # 3. Macro calendar
    macro_provider = build_macro_provider(settings)
    providers_used["macro"] = macro_provider.name
    macro_events = collect_macro_calendar(macro_provider, run_date)

    # 4. Scoring (deterministic, Section 10)
    clusters = score_clusters(clusters, assets_by_symbol, settings)
    eligible_clusters = [c for c in clusters if c.importance.total >= settings.min_story_score]
    logger.info(
        "Scoring: %d clusters total, %d eligible (score >= %.2f)",
        len(clusters), len(eligible_clusters), settings.min_story_score,
    )

    macro_clusters, market_clusters = split_macro_vs_market(eligible_clusters)
    top_macro_clusters = macro_clusters[: settings.macro_stories]
    top_market_clusters = market_clusters[: settings.top_news]

    # 5. LLM analysis
    llm = build_llm_provider(settings)
    providers_used["llm"] = llm.name

    theme_context = {
        t["key"]: {
            "name": t.get("name", t["key"]),
            "drivers": t.get("drivers", []),
            "upstream": t.get("upstream", []),
            "downstream": t.get("downstream", []),
            "risks": t.get("risks", []),
        }
        for t in settings.themes
    }

    regime = infer_market_regime(llm, snapshot, top_market_clusters + top_macro_clusters)
    llm_calls += 1

    theme_views = analyze_themes(llm, settings, snapshot, eligible_clusters)
    llm_calls += 1

    macro_story_analyses = analyze_stories(llm, top_macro_clusters, theme_context)
    llm_calls += 1 if top_macro_clusters else 0

    top_story_analyses = analyze_stories(llm, top_market_clusters, theme_context)
    llm_calls += 1 if top_market_clusters else 0

    company_radar = analyze_companies(llm, eligible_clusters, settings, max_companies=settings.company_radar)
    llm_calls += 1 if company_radar or eligible_clusters else 0

    trade_ideas = generate_trade_ideas(llm, theme_views, company_radar, max_ideas=settings.trade_ideas_max)
    llm_calls += 1

    educational = generate_educational_content(
        llm, regime, top_story_analyses, run_date, max_terms=settings.terminology_terms
    )
    llm_calls += 1
    if settings.educational_mode:
        concepts = [educational.learn_one_thing.title] + [t.term for t in educational.terminology]
        record_concepts_taught(run_date, concepts)

    synthesis = synthesize_report(llm, regime, top_story_analyses, theme_views, trade_ideas)
    llm_calls += 1

    # 6. Yesterday review (optional, Section 22)
    yesterday_items = []
    if settings.yesterday_review:
        prior_ideas = get_prior_trade_ideas(run_date)
        yesterday_items = build_review(prior_ideas, assets_by_symbol)

    # 7. Data quality gate (Section 34)
    quality = run_quality_checks(snapshot, eligible_clusters, top_story_analyses + macro_story_analyses, settings)

    # 8. Source index (per-source tier, tracked directly from the original
    # articles - not approximated from the cluster's best tier).
    seen_sources: Dict[str, Dict[str, Any]] = {}
    for c in eligible_clusters:
        for sid, sname in zip(c.source_ids, c.source_names):
            tier = c.source_tiers.get(sid, c.best_tier)
            existing = seen_sources.get(sid)
            if existing is None or tier < existing["tier"]:
                seen_sources[sid] = {"name": sname, "tier": tier}
    source_index = [
        SourceRecord(
            source_id=sid, source_name=info["name"], tier=SourceTier(info["tier"]),
            kind="unknown", url=None, fetched_at=now_utc(),
        )
        for sid, info in seen_sources.items()
    ]

    # 9. Assemble final report
    report = MorningReport(
        run_date=run_date,
        generated_at=now_utc(),
        timezone=settings.timezone,
        regime=regime,
        three_things_that_matter=synthesis.three_things_that_matter,
        main_risk_today=synthesis.main_risk_today,
        one_sentence_summary=synthesis.one_sentence_summary,
        market_snapshot=snapshot,
        dominant_narrative=synthesis.dominant_narrative,
        macro_events_today=macro_events,
        macro_stories=macro_story_analyses,
        theme_views=theme_views,
        top_stories=top_story_analyses,
        company_radar=company_radar,
        trade_ideas=trade_ideas,
        learn_one_thing=educational.learn_one_thing if settings.educational_mode else None,
        terminology=educational.terminology if settings.educational_mode else [],
        mental_model=synthesis.mental_model,
        yesterday_review=yesterday_items,
        data_quality=quality,
        source_index=source_index,
    )

    # 10. Render HTML (+ compact PDF if that's the configured delivery format)
    html = render_report(report)

    pdf_bytes: Optional[bytes] = None
    if settings.email_format == "pdf":
        try:
            from src.reports.pdf import ChromeNotFoundError, html_to_pdf
            from src.reports.renderer import render_report_pdf_html

            pdf_html = render_report_pdf_html(report)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
                tmp_pdf_path = tmp_pdf.name
            html_to_pdf(pdf_html, tmp_pdf_path)
            with open(tmp_pdf_path, "rb") as f:
                pdf_bytes = f.read()
            os.unlink(tmp_pdf_path)
            logger.info("PDF report rendered (%d bytes)", len(pdf_bytes))
        except ChromeNotFoundError as exc:
            logger.warning("PDF delivery requested but unavailable, falling back to HTML email: %s", exc)
            failures.append(f"pdf_generation_unavailable: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.error("PDF generation failed, falling back to HTML email: %s", exc)
            failures.append(f"pdf_generation_failed: {exc}")

    # 11. Persist (upsert on run_date so re-running the same date - e.g. a
    # manual re-run or a retried scheduled job - overwrites rather than
    # violating the unique run_date constraint).
    with get_session() as session:
        from sqlalchemy import select as _select

        existing_report = session.execute(
            _select(ReportRow).where(ReportRow.run_date == run_date)
        ).scalar_one_or_none()
        if existing_report is not None:
            existing_report.generated_at = datetime.utcnow()
            existing_report.json_payload = dumps(report.model_dump(mode="json"))
            existing_report.degraded_mode = quality.degraded_mode
            existing_report.email_status = "not_sent"
        else:
            session.add(
                ReportRow(
                    run_date=run_date,
                    generated_at=datetime.utcnow(),
                    html_path=None,
                    json_payload=dumps(report.model_dump(mode="json")),
                    degraded_mode=quality.degraded_mode,
                    email_status="not_sent",
                )
            )
        session.query(AnalysisResultRow).filter(
            AnalysisResultRow.run_date == run_date, AnalysisResultRow.kind == "regime"
        ).delete()
        session.query(TradeIdeaRow).filter(TradeIdeaRow.run_date == run_date).delete()
        session.add(
            AnalysisResultRow(run_date=run_date, kind="regime", ref_key=None, payload_json=dumps(regime.model_dump(mode="json")))
        )
        for idea in trade_ideas:
            session.add(
                TradeIdeaRow(
                    run_date=run_date,
                    ticker=idea.ticker,
                    direction=idea.direction.value,
                    thesis=idea.thesis,
                    invalidation_condition=idea.invalidation_condition,
                    reference_price=assets_by_symbol.get(idea.ticker).last_price if idea.ticker in assets_by_symbol else None,
                    confidence_pct=idea.confidence_pct,
                    payload_json=dumps(idea.model_dump(mode="json")),
                )
            )

        # Raw-data tables (Section 28: "store raw data where reasonable so
        # reports are reproducible"). Cleared for this run_date first so a
        # re-run of the same date overwrites cleanly instead of duplicating
        # or hitting the news_articles.article_id unique constraint.
        session.query(MarketSnapshotRow).filter(MarketSnapshotRow.run_date == run_date).delete()
        session.query(NewsArticleRow).filter(NewsArticleRow.run_date == run_date).delete()
        session.query(NewsClusterRow).filter(NewsClusterRow.run_date == run_date).delete()
        session.query(ThemeDailyViewRow).filter(ThemeDailyViewRow.run_date == run_date).delete()
        session.query(CompanyEventRow).filter(CompanyEventRow.run_date == run_date).delete()
        session.query(MacroEventRow).filter(MacroEventRow.run_date == run_date).delete()
        session.query(SourceRecordRow).filter(SourceRecordRow.run_date == run_date).delete()

        for asset in snapshot.assets:
            session.add(
                MarketSnapshotRow(
                    run_date=run_date, symbol=asset.symbol, display_name=asset.display_name,
                    group_name=asset.group, previous_close=asset.previous_close, last_price=asset.last_price,
                    daily_pct=asset.daily_pct, overnight_pct=asset.overnight_pct, volume=asset.volume,
                    relative_volume=asset.relative_volume, return_5d_pct=asset.return_5d_pct,
                    return_1m_pct=asset.return_1m_pct, pct_from_52w_high=asset.pct_from_52w_high,
                    as_of=asset.as_of, data_source=asset.data_source, is_stale=asset.is_stale,
                )
            )
        for art in raw_articles:
            session.add(
                NewsArticleRow(
                    article_id=art.article_id, run_date=run_date, title=art.title, summary=art.summary,
                    body_excerpt=art.body_excerpt, url=art.url, source_id=art.source_id,
                    source_name=art.source_name, tier=art.tier.value, published_at=art.published_at,
                    tickers_json=dumps(art.tickers), themes_json=dumps(art.themes),
                )
            )
        for c in clusters:
            session.add(
                NewsClusterRow(
                    cluster_id=c.cluster_id, run_date=run_date, title=c.title,
                    member_article_ids_json=dumps(c.member_article_ids), tickers_json=dumps(c.tickers),
                    themes_json=dumps(c.themes), importance_json=dumps(c.importance.model_dump(mode="json")),
                    total_score=c.importance.total,
                )
            )
        for t in theme_views:
            session.add(
                ThemeDailyViewRow(
                    run_date=run_date, theme_key=t.theme_key, view=t.view.value, momentum=t.momentum.value,
                    kind=t.kind.value, evidence_json=dumps(t.evidence), risk=t.risk,
                    confidence_pct=t.confidence_pct,
                )
            )
        for c in company_radar:
            session.add(
                CompanyEventRow(
                    run_date=run_date, ticker=c.ticker, company_name=c.company_name, headline=c.headline,
                    relevant_driver=c.relevant_driver.value if c.relevant_driver else None,
                    explanation=c.explanation, confidence_pct=c.confidence_pct,
                )
            )
        for e in macro_events:
            session.add(
                MacroEventRow(
                    run_date=run_date, event=e.event, scheduled_at_sgt=e.scheduled_at_sgt,
                    expected=e.expected, previous=e.previous, actual=e.actual,
                    importance=e.importance.value, notes=e.notes,
                )
            )
        for src in source_index:
            session.add(
                SourceRecordRow(
                    run_date=run_date, source_id=src.source_id, source_name=src.source_name,
                    tier=src.tier.value, kind=src.kind, url=src.url, fetched_at=src.fetched_at,
                )
            )

    # 12. Email
    email_status = "skipped"
    email_path = None
    if send_email:
        email_provider = build_email_provider(settings)
        providers_used["email"] = email_provider.name
        success = send_morning_email(
            email_provider, settings, run_date, html,
            pdf_bytes=pdf_bytes,
            pdf_filename=f"morning_desk_{run_date}.pdf",
            summary=report.one_sentence_summary,
        )
        email_status = "sent" if success else "failed"
        email_path = getattr(email_provider, "last_path", None)
    else:
        # Still write the report to the outbox for inspection even when not sending.
        from pathlib import Path

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        if pdf_bytes is not None:
            email_path = out / f"morning_report_{run_date}.pdf"
            email_path.write_bytes(pdf_bytes)
        else:
            email_path = out / f"morning_report_{run_date}.html"
            email_path.write_text(html, encoding="utf-8")

    with get_session() as session:
        from sqlalchemy import select

        run_row = session.execute(select(SystemRunRow).where(SystemRunRow.run_id == run_id)).scalar_one()
        run_row.ended_at = datetime.utcnow()
        run_row.providers_used_json = dumps(providers_used)
        run_row.articles_collected = articles_collected
        run_row.stories_after_dedup = len(clusters)
        run_row.stories_analyzed = len(top_story_analyses) + len(macro_story_analyses)
        run_row.llm_calls = llm_calls
        run_row.failures_json = dumps(failures)
        run_row.email_status = email_status
        run_row.status = "degraded" if quality.degraded_mode else "success"

        report_row = session.execute(select(ReportRow).where(ReportRow.run_date == run_date)).scalar_one_or_none()
        if report_row is not None:
            report_row.email_status = email_status
            run_row.report_id = report_row.id

    logger.info(
        "=== Morning pipeline finished (run_id=%s): %d articles, %d clusters, %d LLM calls, email=%s ===",
        run_id, articles_collected, len(clusters), llm_calls, email_status,
    )

    return {
        "run_id": run_id,
        "report": report,
        "html": html,
        "email_status": email_status,
        "email_path": str(email_path) if email_path else None,
        "providers_used": providers_used,
    }
