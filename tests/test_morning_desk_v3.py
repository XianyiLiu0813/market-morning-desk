"""Morning Desk v3 redesign tests: the deterministic Key Stats strip
(src/analysis/market_state.py::build_key_stats), the deterministic
Dislocations mock generator (src/providers/mock_llm_responses.py::
_build_key_dislocations), and the new PDF sections that render previously
orphaned MorningReport data (mental_model, source_index) plus the upgraded
evidence-tier callout styling."""
from __future__ import annotations

from datetime import date, datetime, timezone as tz

from src.analysis.market_state import build_key_stats
from src.models.schemas import MarketAsset, MarketSnapshot
from src.providers.mock_llm_responses import _build_key_dislocations
from src.reports.renderer import render_report_pdf_html


def _snapshot(assets: list[MarketAsset]) -> MarketSnapshot:
    return MarketSnapshot(run_date=date(2026, 9, 9), generated_at=datetime.now(tz=tz.utc), assets=assets)


def test_build_key_stats_renders_index_and_rate_cards():
    snapshot = _snapshot([
        MarketAsset(symbol="^GSPC", display_name="S&P 500", group="美股指数", daily_pct=0.73, last_price=7722.72),
        MarketAsset(symbol="^VIX", display_name="VIX", group="波动率", daily_pct=-6.59, last_price=15.31),
        MarketAsset(symbol="US10Y", display_name="US10Y", group="利率", previous_close=5.24, last_price=5.28, is_rate=True),
    ])
    stats = build_key_stats(snapshot)
    labels = {s.label: s for s in stats}
    assert "S&P 500" in labels
    assert labels["S&P 500"].primary == "+0.73%"
    assert labels["S&P 500"].direction == "pos"
    assert "VIX" in labels
    assert labels["VIX"].primary == "15.31"
    assert labels["VIX"].direction == "neg"
    assert "美债 2Y/10Y/30Y" in labels
    assert "5.28" in labels["美债 2Y/10Y/30Y"].primary


def test_build_key_stats_omits_card_for_missing_symbol():
    """A symbol absent from the snapshot must simply not produce a card -
    never a fabricated 'data unavailable' placeholder in this fast-read
    strip (Section 34 principle)."""
    snapshot = _snapshot([
        MarketAsset(symbol="^GSPC", display_name="S&P 500", group="美股指数", daily_pct=0.5, last_price=100.0),
    ])
    stats = build_key_stats(snapshot)
    labels = {s.label for s in stats}
    assert "S&P 500" in labels
    assert "VIX" not in labels
    assert "美债 2Y/10Y/30Y" not in labels
    assert "10Y 实际收益率" not in labels


def test_build_key_stats_includes_real_yield_card_only_when_present():
    with_real_yield = _snapshot([
        MarketAsset(symbol="US10Y_REAL", display_name="10Y实际收益率", group="利率", previous_close=2.88, last_price=2.92, is_rate=True),
        MarketAsset(symbol="US10Y_BREAKEVEN", display_name="10Y盈亏平衡通胀率", group="利率", last_price=2.36, is_rate=True),
    ])
    stats = build_key_stats(with_real_yield)
    labels = {s.label: s for s in stats}
    assert "10Y 实际收益率" in labels
    assert "2.36" in labels["10Y 实际收益率"].secondary

    without_real_yield = _snapshot([])
    assert build_key_stats(without_real_yield) == []


def test_key_dislocations_flags_structural_tactical_disagreement():
    themes = [
        {"name": "AI 算力", "structural_view": "BULLISH", "tactical_view": "BEARISH", "price_confirmation": "确认"},
    ]
    out = _build_key_dislocations(themes)
    assert len(out) == 1
    assert "AI 算力" in out[0]


def test_key_dislocations_flags_price_confirmation_mismatch():
    themes = [
        {"name": "半导体", "structural_view": "BULLISH", "tactical_view": "BULLISH", "price_confirmation": "中性"},
    ]
    out = _build_key_dislocations(themes)
    assert len(out) == 1
    assert "半导体" in out[0]


def test_key_dislocations_empty_when_themes_concordant():
    """No manufactured dislocations when structural/tactical/price all
    agree - matches the mock prompt's "empty list if none today" rule."""
    themes = [
        {"name": "AI 算力", "structural_view": "BULLISH", "tactical_view": "BULLISH", "price_confirmation": "确认"},
        {"name": "黄金", "structural_view": "NEUTRAL", "tactical_view": "NEUTRAL", "price_confirmation": "确认"},
    ]
    assert _build_key_dislocations(themes) == []


def test_key_dislocations_capped_at_three(monkeypatch):
    themes = [
        {"name": f"主题{i}", "structural_view": "BULLISH", "tactical_view": "BEARISH", "price_confirmation": "确认"}
        for i in range(5)
    ]
    out = _build_key_dislocations(themes)
    assert len(out) <= 3


def test_pdf_renders_key_stats_mental_model_and_source_index(minimal_report_kwargs):
    from src.models.schemas import KeyStat, MentalModel, MorningReport, SourceRecord, SourceTier
    from src.utils.time import now_utc

    kwargs = dict(minimal_report_kwargs)
    kwargs["key_stats"] = [KeyStat(label="S&P 500", primary="+0.73%", secondary="7,722.72", direction="pos")]
    kwargs["mental_model"] = MentalModel(
        what_changed="test-what-changed-marker",
        what_did_not_change="x", what_is_market_pricing="x", what_is_consensus="x",
        what_could_market_be_wrong_about="x", what_data_would_change_view="x",
        which_assets_express_view_best="x", is_risk_reward_attractive="x",
    )
    kwargs["source_index"] = [
        SourceRecord(source_id="s1", source_name="SEC EDGAR", tier=SourceTier.PRIMARY, fetched_at=now_utc()),
    ]
    report = MorningReport(**kwargs)
    html = render_report_pdf_html(report)

    assert "S&amp;P 500" in html  # Jinja autoescapes "&" in the HTML output
    assert "+0.73%" in html
    assert "test-what-changed-marker" in html
    assert "分析师思维模型" in html
    assert "SEC EDGAR" in html
    assert "Source Index" in html


def test_pdf_renders_dislocations_section_only_when_present(minimal_report_kwargs):
    from src.models.schemas import EditorialSynthesis, MentalModel, MorningReport

    base_mental_model = MentalModel(
        what_changed="x", what_did_not_change="x", what_is_market_pricing="x", what_is_consensus="x",
        what_could_market_be_wrong_about="x", what_data_would_change_view="x",
        which_assets_express_view_best="x", is_risk_reward_attractive="x",
    )

    kwargs_without = dict(minimal_report_kwargs)
    report_without = MorningReport(**kwargs_without)
    assert "Dislocations" not in render_report_pdf_html(report_without)

    kwargs_with = dict(minimal_report_kwargs)
    kwargs_with["key_dislocations"] = ["半导体：结构性看多但价格确认为中性，值得继续跟踪。"]
    # key_dislocations lives on EditorialSynthesis in the pipeline, but on
    # MorningReport itself it's a plain field - construct directly.
    report_with = MorningReport(**kwargs_with)
    html_with = render_report_pdf_html(report_with)
    assert "Dislocations" in html_with
    assert "半导体" in html_with
