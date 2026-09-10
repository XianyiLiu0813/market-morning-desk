"""Deterministic price-confirmation helper (V2 Part 9).

"News is only one input" - a story or company write-up must show how the
relevant tickers ACTUALLY traded, not let the LLM describe/guess at price
action. This module reads directly from the validated MarketSnapshot
(Part 3) and formats a price_check list; it is never passed through an
LLM call, so it cannot hallucinate a number that isn't in the snapshot.
"""
from __future__ import annotations

from typing import List

from src.models.schemas import MarketSnapshot


def price_check_for_tickers(snapshot: MarketSnapshot, tickers: List[str]) -> List[str]:
    """Return e.g. ["NVDA +0.5%", "SMH -0.6%"] for whichever of `tickers`
    have valid daily_pct data in the snapshot. Tickers with no data are
    silently omitted (not shown as "0%" or invented) - an empty result
    means "no relevant ticker had price data", which callers should render
    as "数据不足" rather than leaving the section blank with no
    explanation."""
    out: List[str] = []
    for ticker in tickers:
        asset = snapshot.get(ticker)
        if asset is None or asset.daily_pct is None:
            continue
        sign = "+" if asset.daily_pct > 0 else ""
        out.append(f"{ticker} {sign}{asset.daily_pct:.2f}%")
    return out


def summarize_price_confirmation(price_check: List[str], theme_view: str) -> str:
    """Rule-based READ of a price_check list against a claimed
    view/direction - e.g. "confirmed", "mixed", "contradicted". Used for
    the ThemeView.price_confirmation column and story-level confirmation
    text. Deterministic, not LLM-generated, for the same hallucination-
    avoidance reason as price_check_for_tickers()."""
    if not price_check:
        return "数据不足"

    moves = []
    for item in price_check:
        try:
            pct_str = item.rsplit(" ", 1)[-1].rstrip("%")
            moves.append(float(pct_str))
        except (ValueError, IndexError):
            continue
    if not moves:
        return "数据不足"

    avg_move = sum(moves) / len(moves)
    bullish_claim = theme_view.upper() in ("BULLISH", "SLIGHTLY_BULLISH", "POSITIVE")
    bearish_claim = theme_view.upper() in ("BEARISH", "SLIGHTLY_BEARISH", "NEGATIVE")

    spread = max(moves) - min(moves) if len(moves) > 1 else 0.0
    if spread > 2.5:
        return "分化"  # relevant tickers moved in different directions
    if bullish_claim and avg_move > 0.3:
        return "确认"
    if bearish_claim and avg_move < -0.3:
        return "确认"
    if bullish_claim and avg_move < -0.3:
        return "背离"
    if bearish_claim and avg_move > 0.3:
        return "背离"
    return "中性"
