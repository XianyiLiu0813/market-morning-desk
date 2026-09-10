"""Trader's Dashboard (V2 Part 5) - deterministic, rule-based market-state
read computed directly from the validated snapshot. This is intentionally
NOT an LLM call: six coarse states (risk appetite / rates / USD /
volatility / breadth / liquidity) are exactly the kind of thing a simple,
auditable threshold rule does better than a model - no risk of the wording
drifting inconsistently from the actual numbers.

Two of the six dimensions (breadth, liquidity) do not have a clean direct
data source in this system (no advance/decline data, no credit-spread
feed), so they are explicitly labeled as proxies rather than presented as
if they were measured directly - see TraderDashboard.breadth_is_proxy /
liquidity_is_proxy in schemas.py, and Section 34's "never pretend missing
data exists" principle.
"""
from __future__ import annotations

from typing import Optional

from src.models.schemas import MarketSnapshot, TraderDashboard


def _g(snapshot: MarketSnapshot, symbol: str) -> Optional[float]:
    asset = snapshot.get(symbol)
    return asset.daily_pct if asset else None


def _bp(snapshot: MarketSnapshot, symbol: str) -> Optional[float]:
    asset = snapshot.get(symbol)
    return asset.bp_change if asset else None


def compute_trader_dashboard(snapshot: MarketSnapshot) -> TraderDashboard:
    spy = _g(snapshot, "SPY")
    iwm = _g(snapshot, "IWM")
    vix = _g(snapshot, "^VIX")
    us10y_bp = _bp(snapshot, "US10Y")
    us2y_bp = _bp(snapshot, "US2Y")
    dxy = _g(snapshot, "DXY")

    # --- Risk appetite: broad equity participation + falling vol ---
    if spy is not None and vix is not None:
        if spy > 0.3 and vix < -3:
            risk_appetite = "改善"
        elif spy < -0.3 and vix > 3:
            risk_appetite = "恶化"
        else:
            risk_appetite = "稳定"
    else:
        risk_appetite = "数据不足"

    # --- Rates: use the 10Y bp move as the primary read ---
    if us10y_bp is not None:
        if us10y_bp >= 3:
            rates = "上行"
        elif us10y_bp <= -3:
            rates = "下行"
        else:
            rates = "持平"
    else:
        rates = "数据不足"

    # --- USD ---
    if dxy is not None:
        if dxy > 0.2:
            usd = "走强"
        elif dxy < -0.2:
            usd = "走弱"
        else:
            usd = "持平"
    else:
        usd = "数据不足"

    # --- Volatility ---
    if vix is not None:
        if vix <= -3:
            volatility = "下降"
        elif vix >= 3:
            volatility = "上升"
        else:
            volatility = "持平"
    else:
        volatility = "数据不足"

    # --- Breadth (proxy): small caps (IWM) vs large caps (SPY) spread.
    # A genuine advance/decline line would be better; this is a rough
    # stand-in using what's already in the asset universe.
    if spy is not None and iwm is not None:
        spread = iwm - spy
        if spread > 0.3:
            breadth = "偏宽"
        elif spread < -0.5:
            breadth = "偏窄"
        else:
            breadth = "分化"
    else:
        breadth = "数据不足"

    # --- Liquidity (proxy): no direct credit-spread/repo feed in this
    # system: proxy from VIX direction + 2Y yield direction, both of which
    # move with financial-conditions tightening/easing more often than not.
    if vix is not None and us2y_bp is not None:
        if vix <= -3 and us2y_bp <= 0:
            liquidity = "支持性"
        elif vix >= 3 and us2y_bp >= 3:
            liquidity = "收紧"
        else:
            liquidity = "中性"
    else:
        liquidity = "数据不足"

    return TraderDashboard(
        risk_appetite=risk_appetite,
        rates=rates,
        usd=usd,
        volatility=volatility,
        breadth=breadth,
        liquidity=liquidity,
        breadth_is_proxy=True,
        liquidity_is_proxy=True,
    )
