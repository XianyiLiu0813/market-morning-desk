"""Market regime inference tests (Section 35) - uses MockLLMProvider so no
external API is needed."""
from __future__ import annotations

from datetime import date, datetime, timezone

from src.analysis.market_regime import infer_market_regime
from src.models.schemas import MarketAsset, MarketSnapshot, RegimeLabel
from src.providers.mock_providers import MockLLMProvider


def make_snapshot(overrides):
    base = {
        "^GSPC": 0.1, "^IXIC": 0.1, "^RUT": 0.1, "^HSI": 0.1, "^HSTECH": 0.1,
        "^VIX": 0.0, "US10Y": 0.0, "US2Y": 0.0, "DXY": 0.0, "QQQ": 0.1,
        "SMH": 0.1, "SOXX": 0.1, "IWM": 0.1, "XLK": 0.1, "GLD": 0.0, "CL=F": 0.0, "KWEB": 0.0,
    }
    base.update(overrides)
    assets = [
        MarketAsset(symbol=sym, display_name=sym, group="g", daily_pct=pct)
        for sym, pct in base.items()
    ]
    return MarketSnapshot(run_date=date(2026, 9, 9), generated_at=datetime.now(tz=timezone.utc), assets=assets)


def test_concentrated_ai_move_labeled_ai_led():
    snapshot = make_snapshot({"SMH": 4.0, "^RUT": 0.1, "^GSPC": 0.5})
    llm = MockLLMProvider()
    regime = infer_market_regime(llm, snapshot, [])
    assert RegimeLabel.AI_LED in regime.labels


def test_broad_rally_labeled_risk_on():
    snapshot = make_snapshot({"^GSPC": 1.0, "^RUT": 1.0, "^VIX": -3.0, "SMH": 1.0})
    llm = MockLLMProvider()
    regime = infer_market_regime(llm, snapshot, [])
    assert RegimeLabel.RISK_ON in regime.labels


def test_regime_confidence_in_valid_range():
    snapshot = make_snapshot({})
    llm = MockLLMProvider()
    regime = infer_market_regime(llm, snapshot, [])
    assert 0 <= regime.confidence_pct <= 100


def test_regime_returns_safe_fallback_on_llm_failure(monkeypatch):
    snapshot = make_snapshot({})

    class BrokenLLM(MockLLMProvider):
        def generate_json(self, *args, **kwargs):
            raise RuntimeError("simulated provider outage")

    regime = infer_market_regime(BrokenLLM(), snapshot, [])
    assert regime.confidence_pct == 0
    assert RegimeLabel.MIXED in regime.labels
