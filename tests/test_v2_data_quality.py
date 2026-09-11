"""V2 Part 2/32 data-quality tests: NaN never reaches the report, rates
display as level+bp, core-asset gate fires correctly (Part 33 Case D/E/F)."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone as tz

from src.models.schemas import MarketAsset, MarketSnapshot
from src.processing.quality import check_core_assets, run_quality_checks
from src.reports.renderer import _fmt_bp, _fmt_pct


def test_market_asset_coerces_nan_to_none():
    """CASE: a provider hands back NaN (e.g. yfinance's incomplete-today-row
    quirk) - the report must display 'data unavailable', never 'nan%'."""
    asset = MarketAsset(symbol="QQQ", display_name="QQQ", group="g", daily_pct=float("nan"))
    assert asset.daily_pct is None


def test_market_asset_coerces_inf_to_none():
    asset = MarketAsset(symbol="QQQ", display_name="QQQ", group="g", daily_pct=float("inf"))
    assert asset.daily_pct is None


def test_fmt_pct_never_renders_nan_literal():
    assert _fmt_pct(float("nan")) == "数据暂缺"
    assert _fmt_pct(None) == "数据暂缺"
    assert "nan" not in _fmt_pct(float("nan")).lower()


def test_rate_asset_bp_change_computed_correctly():
    """CASE D (Part 33): US10Y rises from 4.00% to 4.05% must display as
    '+5bp', never as '+1.25%'."""
    asset = MarketAsset(
        symbol="US10Y", display_name="US10Y", group="利率",
        previous_close=4.00, last_price=4.05, is_rate=True,
    )
    assert asset.bp_change == 5.0
    assert _fmt_bp(asset) == "+5.0bp"


def test_non_rate_asset_has_no_bp_change():
    asset = MarketAsset(symbol="QQQ", display_name="QQQ", group="g", previous_close=100, last_price=101, is_rate=False)
    assert asset.bp_change is None


def _core_snapshot(missing_symbols=None, stale_symbols=None):
    missing_symbols = missing_symbols or []
    stale_symbols = stale_symbols or []
    core = ["SPY", "QQQ", "IWM", "SMH", "SOXX", "^VIX", "US2Y", "US10Y", "DXY", "GC=F", "CL=F", "BTC-USD", "^HSI", "^HSTECH", "KWEB"]
    assets = []
    for sym in core:
        if sym in missing_symbols:
            continue
        is_rate = sym in ("US2Y", "US10Y")
        asset = MarketAsset(
            symbol=sym, display_name=sym, group="g",
            last_price=100.0, previous_close=99.0,
            daily_pct=None if is_rate else 1.0,
            is_rate=is_rate,
            is_stale=sym in stale_symbols,
        )
        assets.append(asset)
    return MarketSnapshot(run_date=date(2026, 9, 9), generated_at=datetime.now(tz=tz.utc), assets=assets)


def test_core_assets_all_present_means_no_missing(settings):
    snapshot = _core_snapshot()
    missing = check_core_assets(snapshot, settings)
    assert missing == []


def test_core_assets_missing_symbol_detected(settings):
    snapshot = _core_snapshot(missing_symbols=["QQQ", "SMH"])
    missing = check_core_assets(snapshot, settings)
    assert set(missing) == {"QQQ", "SMH"}


def test_core_assets_stale_symbol_counted_as_missing(settings):
    snapshot = _core_snapshot(stale_symbols=["SPY"])
    missing = check_core_assets(snapshot, settings)
    assert "SPY" in missing


def _dummy_cluster():
    from src.models.schemas import NewsCluster

    return NewsCluster(
        cluster_id="c1", representative_article_id="a1", member_article_ids=["a1"],
        title="dummy", urls=["https://example.com"], best_tier=1,
    )


def test_degraded_mode_when_too_many_core_assets_missing(settings):
    """CASE E/F (Part 33): if more than max_core_assets_missing core
    symbols are unavailable, the report must be marked degraded rather
    than silently presented as normal."""
    snapshot = _core_snapshot(missing_symbols=["QQQ", "SMH", "SOXX", "IWM", "SPY"])
    status = run_quality_checks(snapshot, [_dummy_cluster()], [], settings)
    assert status.degraded_mode is True
    assert len(status.core_assets_missing) == 5


def test_not_degraded_when_few_core_assets_missing(settings):
    snapshot = _core_snapshot(missing_symbols=["QQQ"])
    status = run_quality_checks(snapshot, [_dummy_cluster()], [], settings)
    assert status.degraded_mode is False
    assert "QQQ" in status.core_assets_missing


def test_same_article_across_two_days_does_not_crash(tmp_db):
    """Reproduces a real production crash: an RSS feed can still list the
    same article (identical source_id/url/title, hence identical
    deterministic article_id hash) across two consecutive daily runs -
    e.g. published late in the prior day, still within the collection
    window the next morning. The per-run cleanup in pipeline.py only
    deletes THAT day's rows before re-inserting, so article_id must be
    unique per (run_date, article_id), not globally unique, or the second
    day's insert crashes the whole pipeline with an IntegrityError."""
    from datetime import date

    from src.models.database import NewsArticleRow, get_session

    with get_session() as session:
        session.add(NewsArticleRow(
            article_id="dup123", run_date=date(2026, 9, 10), title="Same article",
            source_id="nikkei", source_name="Nikkei Asia", tier=2,
            tickers_json="[]", themes_json="[]",
        ))

    # Must not raise - this is the exact scenario that crashed production.
    with get_session() as session:
        session.add(NewsArticleRow(
            article_id="dup123", run_date=date(2026, 9, 11), title="Same article",
            source_id="nikkei", source_name="Nikkei Asia", tier=2,
            tickers_json="[]", themes_json="[]",
        ))
