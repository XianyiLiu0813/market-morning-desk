"""Real MarketDataProvider implementation using yfinance.

yfinance is free/keyless but scrapes Yahoo Finance endpoints, so treat it
as best-effort: wrap every call in retry_with_backoff and let the
collector layer degrade gracefully on failure (Section 27/34). For
production-grade reliability, swap in Polygon.io or Finnhub (both have
official REST APIs) by implementing the same MarketDataProvider interface.
"""
from __future__ import annotations

import logging
from typing import List

from src.models.schemas import MarketAsset
from src.providers.market_base import MarketDataProvider
from src.utils.retry import retry_with_backoff
from src.utils.time import now_utc

logger = logging.getLogger("morning_desk")

# Symbols in config/assets.yaml that aren't valid Yahoo Finance tickers as-is
# (Treasury yields, DXY, USD/CNH) need remapping to Yahoo's convention.
YAHOO_SYMBOL_MAP = {
    "US2Y": "^IRX",  # NOTE: ^IRX is actually 13-week T-bill; true 2Y/10Y/30Y
    "US10Y": "^TNX",  # yield series on Yahoo are ^TNX (10Y) and ^TYX (30Y).
    "US30Y": "^TYX",  # US2Y/2s10s have no clean free Yahoo ticker - a
    "US2S10S": None,  # dedicated rates API (FRED) is recommended for those.
    "DXY": "DX-Y.NYB",
    "USDCNH": "USDCNH=X",
    "USDJPY": "USDJPY=X",
    # "^HSTECH" (the index code used in config/assets.yaml) 404s on Yahoo;
    # "HSTECH.HK" is the tracker symbol Yahoo actually serves data for.
    "^HSTECH": "HSTECH.HK",
}


class YFinanceMarketDataProvider(MarketDataProvider):
    name = "yfinance"

    @retry_with_backoff(max_attempts=3, exceptions=(Exception,))
    def get_snapshot(self, symbols: List[str]) -> List[MarketAsset]:
        import yfinance as yf

        out: List[MarketAsset] = []
        resolved = {}
        for sym in symbols:
            mapped = YAHOO_SYMBOL_MAP.get(sym, sym)
            if mapped is None:
                continue
            resolved[mapped] = sym

        if not resolved:
            return out

        tickers = yf.Tickers(" ".join(resolved.keys()))
        as_of = now_utc()
        for yahoo_sym, original_sym in resolved.items():
            try:
                t = tickers.tickers.get(yahoo_sym)
                if t is None:
                    continue
                hist = t.history(period="3mo", interval="1d")
                if hist.empty:
                    continue
                last = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else last
                last_price = float(last["Close"])
                previous_close = float(prev["Close"])
                daily_pct = (
                    (last_price - previous_close) / previous_close * 100
                    if previous_close
                    else None
                )
                ret_5d = None
                if len(hist) > 5:
                    base = float(hist.iloc[-6]["Close"])
                    ret_5d = (last_price - base) / base * 100 if base else None
                ret_1m = None
                if len(hist) > 21:
                    base = float(hist.iloc[-22]["Close"])
                    ret_1m = (last_price - base) / base * 100 if base else None
                high_52w = float(hist["Close"].max())
                pct_from_high = (
                    (last_price - high_52w) / high_52w * 100 if high_52w else None
                )
                volume = float(last["Volume"]) if "Volume" in last else None
                avg_volume = float(hist["Volume"].tail(20).mean()) if "Volume" in hist else None
                rel_volume = (volume / avg_volume) if (volume and avg_volume) else None

                out.append(
                    MarketAsset(
                        symbol=original_sym,
                        display_name=original_sym,
                        group="",
                        previous_close=previous_close,
                        last_price=last_price,
                        daily_pct=daily_pct,
                        overnight_pct=None,
                        volume=volume,
                        relative_volume=rel_volume,
                        return_5d_pct=ret_5d,
                        return_1m_pct=ret_1m,
                        pct_from_52w_high=pct_from_high,
                        as_of=as_of,
                        data_source="yfinance",
                        is_stale=False,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("yfinance failed for %s (%s): %s", original_sym, yahoo_sym, exc)
                continue
        return out
