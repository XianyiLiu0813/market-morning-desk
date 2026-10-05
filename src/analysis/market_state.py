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

from typing import List, Optional

from src.models.schemas import KeyStat, MarketSnapshot, TraderDashboard


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


def _fmt_pct(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"


def _fmt_level(v: Optional[float], decimals: int = 2, thousands: bool = False) -> Optional[str]:
    if v is None:
        return None
    fmt = f"{{:,.{decimals}f}}" if thousands else f"{{:.{decimals}f}}"
    return fmt.format(v)


def _fmt_bp(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.1f}bp"


def _direction(v: Optional[float]) -> Optional[str]:
    if v is None or v == 0:
        return None
    return "pos" if v > 0 else "neg"


def _index_stat(snapshot: MarketSnapshot, symbol: str, label: str) -> Optional[KeyStat]:
    asset = snapshot.get(symbol)
    if asset is None or asset.daily_pct is None:
        return None
    return KeyStat(
        label=label,
        primary=_fmt_pct(asset.daily_pct),
        secondary=_fmt_level(asset.last_price, 2, thousands=True),
        direction=_direction(asset.daily_pct),
    )


def build_key_stats(snapshot: MarketSnapshot) -> List[KeyStat]:
    """Deterministic "headline numbers" strip (Part: borrowed from a sample
    morning note's top-of-page stat grid) - the raw figures a trader
    registers before any interpretation, complementing (not replacing)
    TraderDashboard's interpreted state words. A card is simply omitted if
    its underlying asset is missing from the snapshot (never a fabricated
    "data unavailable" placeholder cluttering this fast-read strip - the
    detailed 隔夜市场仪表盘 tables further down already carry that)."""
    stats: List[KeyStat] = []

    for symbol, label in (("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^RUT", "Russell 2000")):
        stat = _index_stat(snapshot, symbol, label)
        if stat:
            stats.append(stat)

    vix = snapshot.get("^VIX")
    if vix is not None and vix.last_price is not None:
        stats.append(KeyStat(
            label="VIX",
            primary=_fmt_level(vix.last_price, 2),
            secondary=_fmt_pct(vix.daily_pct),
            direction=_direction(vix.daily_pct),
        ))

    us2y, us10y, us30y = snapshot.get("US2Y"), snapshot.get("US10Y"), snapshot.get("US30Y")
    if us10y is not None and us10y.last_price is not None:
        curve_bits = []
        if us2y is not None and us2y.last_price is not None:
            curve_bits.append(f"{us2y.last_price:.2f}")
        curve_bits.append(f"{us10y.last_price:.2f}")
        if us30y is not None and us30y.last_price is not None:
            curve_bits.append(f"{us30y.last_price:.2f}")
        stats.append(KeyStat(
            label="美债 2Y/10Y/30Y",
            primary=" / ".join(curve_bits) + "%",
            secondary=(f"10Y {_fmt_bp(us10y.bp_change)}" if us10y.bp_change is not None else None),
            direction=_direction(us10y.bp_change),
        ))

    real_yield = snapshot.get("US10Y_REAL")
    if real_yield is not None and real_yield.last_price is not None:
        breakeven = snapshot.get("US10Y_BREAKEVEN")
        stats.append(KeyStat(
            label="10Y 实际收益率",
            primary=f"{real_yield.last_price:.2f}%",
            secondary=(
                f"盈亏平衡通胀 {breakeven.last_price:.2f}%"
                if breakeven is not None and breakeven.last_price is not None else
                _fmt_bp(real_yield.bp_change)
            ),
            direction=_direction(real_yield.bp_change),
        ))

    dxy, usdjpy = snapshot.get("DXY"), snapshot.get("USDJPY")
    if dxy is not None and dxy.last_price is not None:
        stats.append(KeyStat(
            label="DXY / USDJPY",
            primary=f"{dxy.last_price:.2f}" + (f" / {usdjpy.last_price:.2f}" if usdjpy and usdjpy.last_price is not None else ""),
            secondary=_fmt_pct(dxy.daily_pct),
            direction=_direction(dxy.daily_pct),
        ))

    wti, brent = snapshot.get("CL=F"), snapshot.get("BZ=F")
    if wti is not None and wti.last_price is not None:
        stats.append(KeyStat(
            label="WTI / Brent",
            primary=f"${wti.last_price:.2f}" + (f" / ${brent.last_price:.2f}" if brent and brent.last_price is not None else ""),
            secondary=_fmt_pct(wti.daily_pct),
            direction=_direction(wti.daily_pct),
        ))

    return stats
