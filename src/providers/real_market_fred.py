"""Optional FRED-sourced market data: 10Y TIPS real yield and breakeven
inflation.

Yahoo Finance (yfinance) doesn't carry a clean TIPS/real-yield series, but
decomposing the nominal 10Y yield into real yield + breakeven inflation is
a genuinely useful read a professional morning note does (e.g. "the
afternoon yield reversal was mostly a real-rate/term-premium move, not an
inflation-expectations move"). FRED has both series free, daily:

  DFII10  - 10-Year Treasury Inflation-Indexed Security, Constant
            Maturity (the real yield itself)
  T10YIE  - 10-Year Breakeven Inflation Rate (nominal - real; the market's
            implied inflation expectation)

This only activates when FRED_API_KEY is set (same optional-key pattern as
real_macro.py's FredMacroProvider) - collectors/market.py calls
fetch_real_yield_assets() and merges the result into the snapshot; if the
key is missing or the request fails, it returns an empty list and the
report simply doesn't show this row, rather than a "data unavailable"
placeholder cluttering the dashboard for a key most users won't have.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from src.models.schemas import MarketAsset
from src.utils.retry import retry_with_backoff
from src.utils.time import now_utc

logger = logging.getLogger("morning_desk")

# series_id -> (symbol, display_name)
REAL_YIELD_SERIES = {
    "DFII10": ("US10Y_REAL", "10Y实际收益率"),
    "T10YIE": ("US10Y_BREAKEVEN", "10Y盈亏平衡通胀率"),
}


@retry_with_backoff(max_attempts=2)
def _fetch_series_last_two(series_id: str, api_key: str) -> Optional[List[float]]:
    """Returns [previous_value, latest_value] (chronological order),
    skipping any missing/non-numeric observations FRED marks with ".", or
    None if fewer than 2 valid observations are available."""
    import requests

    resp = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 10,  # a few extra in case of recent "." (not-yet-published) gaps
        },
        timeout=10,
    )
    resp.raise_for_status()
    obs = resp.json().get("observations", [])
    values = []
    for row in obs:
        v = row.get("value")
        if v and v != ".":
            values.append(float(v))
        if len(values) >= 2:
            break
    if len(values) < 2:
        return None
    return [values[1], values[0]]  # [previous, latest]


def fetch_real_yield_assets(api_key: Optional[str] = None) -> List[MarketAsset]:
    api_key = api_key or os.environ.get("FRED_API_KEY")
    if not api_key:
        return []

    out: List[MarketAsset] = []
    as_of = now_utc()
    for series_id, (symbol, display_name) in REAL_YIELD_SERIES.items():
        try:
            values = _fetch_series_last_two(series_id, api_key)
            if values is None:
                continue
            previous_close, last_price = values
            daily_pct = (
                (last_price - previous_close) / previous_close * 100 if previous_close else None
            )
            out.append(
                MarketAsset(
                    symbol=symbol,
                    display_name=display_name,
                    group="利率",
                    previous_close=previous_close,
                    last_price=last_price,
                    daily_pct=daily_pct,
                    as_of=as_of,
                    data_source="fred",
                    is_rate=True,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("FRED real-yield fetch failed for %s: %s", series_id, exc)
            continue
    return out
