"""V2 Part 33 mock scenario tests - the exact cases specced out in the V2
upgrade request, using the deterministic MockLLMProvider so no external
API is required."""
from __future__ import annotations

from datetime import date, datetime, timezone as tz

from src.analysis.theme_analysis import analyze_themes
from src.analysis.trade_analysis import evaluate_conditions, generate_trade_ideas, passes_threshold
from src.models.schemas import MarketAsset, MarketSnapshot, NewsCluster, TradeDirection, TradeIdea
from src.providers.mock_providers import MockLLMProvider
from src.utils.config import get_settings


def _snapshot(prices: dict) -> MarketSnapshot:
    assets = [
        MarketAsset(symbol=sym, display_name=sym, group="g", daily_pct=pct)
        for sym, pct in prices.items()
    ]
    return MarketSnapshot(run_date=date(2026, 9, 9), generated_at=datetime.now(tz=tz.utc), assets=assets)


def _ai_capex_cluster() -> NewsCluster:
    return NewsCluster(
        cluster_id="c_capex", representative_article_id="a1", member_article_ids=["a1"],
        title="Hyperscaler raises AI capex guidance", tickers=["NVDA"], themes=["ai_compute"],
        urls=["https://example.com"], best_tier=1, fact_hint="AI capex guidance raised.",
    )


def test_case_a_positive_news_but_price_diverges_yields_cautious_tactical(settings):
    """Part 33 Case A: positive AI capex news, BUT SMH/QQQ falling and
    US10Y/VIX rising. Expected: structural view stays supportive (the news
    itself is a real catalyst), tactical view must NOT be a blanket
    LONG-worthy BULLISH - price should not confirm the narrative."""
    snapshot = _snapshot({"SMH": -1.8, "QQQ": -1.2, "US10Y": 0.8, "^VIX": 4.5})
    llm = MockLLMProvider()
    themes = analyze_themes(llm, settings, snapshot, [_ai_capex_cluster()])
    ai_compute = next((t for t in themes if t.theme_key == "ai_compute"), None)
    assert ai_compute is not None, "ai_compute theme should be produced given a matching cluster"
    # Structural: driven by the fundamental narrative, not today's tape.
    assert ai_compute.structural_view.value in ("BULLISH", "SLIGHTLY_BULLISH")
    # Tactical: price did NOT confirm - must not be a bullish tactical read.
    assert ai_compute.tactical_view.value not in ("BULLISH",)
    assert ai_compute.price_confirmation in ("背离", "分化", "数据不足")


def test_case_a_no_forced_long_watch_from_diverging_price(settings):
    """The tightened Part 14 trade-idea gate requires BOTH structural AND
    tactical to be supportive before a company tied to that theme can
    become a trade idea - a structurally-bullish-but-tactically-weak theme
    must not spawn a LONG WATCH."""
    from src.models.schemas import CompanyAnalysis, CompanySignal, ThemeView, Sentiment, Momentum

    weak_theme = ThemeView(
        theme_key="ai_compute", theme_name="AI Compute",
        structural_view=Sentiment.BULLISH, tactical_view=Sentiment.NEUTRAL,
        momentum=Momentum.UNCHANGED, structural_reason="x", tactical_reason="y",
        price_confirmation="背离",
    )
    company = CompanyAnalysis(
        ticker="NVDA", company_name="NVIDIA", signal=CompanySignal.POSITIVE,
        what_changed="capex news", driver_explanation="...", theme_keys=["ai_compute"],
        confidence_pct=80,
    )
    llm = MockLLMProvider()
    ideas = generate_trade_ideas(llm, [weak_theme], [company], max_ideas=3)
    assert ideas == [], "a tactically-neutral/diverging theme must not produce a trade idea"


def test_case_c_no_causal_short_from_unrelated_crypto_crash(settings):
    """Part 33 Case C: a memecoin crash with BTC/ETH themselves unchanged
    must not spawn a BTC/ETH short - there's no theme/company evidence
    connecting the two, so generate_trade_ideas naturally produces nothing
    for BTC/ETH (this test documents that absence-of-evidence behavior)."""
    from src.models.schemas import ThemeView, Sentiment, Momentum

    crypto_theme = ThemeView(
        theme_key="crypto", theme_name="Crypto",
        structural_view=Sentiment.NEUTRAL, tactical_view=Sentiment.NEUTRAL,
        momentum=Momentum.UNCHANGED, structural_reason="x", tactical_reason="y",
        price_confirmation="数据不足",
    )
    llm = MockLLMProvider()
    ideas = generate_trade_ideas(llm, [crypto_theme], [], max_ideas=3)
    assert ideas == []


def test_trade_idea_evidence_gate_requires_three_of_five_conditions():
    strong_idea = TradeIdea(
        ticker="NVDA", direction=TradeDirection.LONG_WATCH,
        catalyst="Hyperscaler capex guidance raised materially",
        confirmation_required="NVDA needs to show relative strength / price confirmation vs peers",
        edge_or_mispricing="Market may be underestimating forward bookings",
        risk_reward="Qualitatively favorable given asymmetric upside vs limited downside",
        invalidation_condition="If price fails to confirm within 3 sessions",
    )
    assert passes_threshold(strong_idea) is True
    assert len(strong_idea.conditions_met) >= 3


def test_trade_idea_evidence_gate_rejects_weak_candidate():
    weak_idea = TradeIdea(ticker="NVDA", direction=TradeDirection.LONG_WATCH)
    assert passes_threshold(weak_idea) is False
    assert weak_idea.conditions_met == []


def test_trade_idea_gate_rejects_no_clear_edge():
    idea = TradeIdea(
        ticker="NVDA", direction=TradeDirection.LONG_WATCH,
        catalyst="Some catalyst here",
        confirmation_required="price confirmation needed",
        edge_or_mispricing="no clear edge today",  # explicit "nothing special" case
        risk_reward="unclear",
        invalidation_condition="if thesis fails",
    )
    conditions = evaluate_conditions(idea)
    assert "expectations_changing" not in conditions
