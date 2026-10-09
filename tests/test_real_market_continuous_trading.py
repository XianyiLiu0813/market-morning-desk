"""Regression test for a real production data-accuracy bug: continuously-
traded instruments (commodity futures, FX, crypto) silently reported the
wrong-sign/wrong-magnitude daily change because yfinance's data for these
symbols had already rolled into a same-day in-progress bar/quote by the
time the SGT morning run fires, while equities/yields (defined trading
session, still closed at that hour) had not.

Caught by cross-checking a real production report (2026-10-08 session)
against an independent third-party report: WTI showed -0.6%..-1.0% in our
report on a day it had actually closed +3.6% (confirmed against yfinance's
own history() daily bar and the independent source). Root cause: (1) the
regularMarketPrice/regularMarketPreviousClose "fix" in
src/providers/real_market.py (added for an earlier equity post-market-drift
bug) was applied unconditionally to ALL symbols, including commodities/FX/
crypto where it measures a different, already-rolled-over window; (2)
history()'s last row can itself already be a same-day in-progress bar for
these symbols by the time the SGT morning run fires.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from src.providers.real_market import YFinanceMarketDataProvider


def _fake_history(rows: dict) -> pd.DataFrame:
    """rows: {date_str: close_price} -> a minimal OHLC DataFrame yfinance-
    shaped enough for get_snapshot to process."""
    index = pd.to_datetime(list(rows.keys()))
    closes = list(rows.values())
    return pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": [0] * len(closes)},
        index=index,
    )


def _patch_tickers(history_by_symbol: dict, info_by_symbol: dict):
    fake_tickers = {}
    for sym, rows in history_by_symbol.items():
        fake_ticker = MagicMock()
        fake_ticker.history.return_value = _fake_history(rows)
        fake_ticker.info = info_by_symbol.get(sym, {})
        fake_tickers[sym] = fake_ticker

    fake_tickers_container = MagicMock()
    fake_tickers_container.tickers = fake_tickers
    return patch("yfinance.Tickers", return_value=fake_tickers_container)


def test_continuous_trading_symbol_uses_pre_run_date_session_not_in_progress_bar():
    """CL=F (WTI) with a same-day in-progress Oct-9 bar already present at
    query time must still compute Oct-8-vs-Oct-7 (+3.6%-ish), not
    Oct-9-partial-vs-Oct-8 (which would show a spurious decline)."""
    history_by_symbol = {
        "CL=F": {
            "2026-10-06": 89.44,
            "2026-10-07": 88.28,
            "2026-10-08": 91.49,  # the session this report should reflect
            "2026-10-09": 90.59,  # in-progress bar at query time - must be dropped
        },
    }
    # Even if regularMarketPrice/regularMarketPreviousClose point at the
    # wrong (already-rolled-forward) window, the fix must not use them for
    # a symbol in CONTINUOUS_TRADING_SYMBOLS.
    info_by_symbol = {"CL=F": {"regularMarketPrice": 90.59, "regularMarketPreviousClose": 91.49}}

    with _patch_tickers(history_by_symbol, info_by_symbol):
        provider = YFinanceMarketDataProvider()
        assets = provider.get_snapshot(["CL=F"], run_date=date(2026, 10, 9))

    assert len(assets) == 1
    asset = assets[0]
    assert asset.last_price == 91.49
    assert asset.previous_close == 88.28
    assert asset.daily_pct > 3.0  # ~+3.6%, not negative


def test_equity_symbol_unaffected_by_run_date_filter_when_no_in_progress_bar():
    """^GSPC has no same-day row yet at query time (defined session, still
    closed) - the run_date filter must be a no-op here."""
    history_by_symbol = {
        "^GSPC": {
            "2026-10-07": 7801.77,
            "2026-10-08": 7765.36,
        },
    }
    info_by_symbol = {"^GSPC": {"regularMarketPrice": 7765.36, "regularMarketPreviousClose": 7801.77}}

    with _patch_tickers(history_by_symbol, info_by_symbol):
        provider = YFinanceMarketDataProvider()
        assets = provider.get_snapshot(["^GSPC"], run_date=date(2026, 10, 9))

    assert len(assets) == 1
    asset = assets[0]
    assert asset.last_price == 7765.36
    assert asset.previous_close == 7801.77
    assert asset.daily_pct < 0


def test_continuous_trading_symbol_without_run_date_falls_back_to_last_row():
    """Backward compatibility: callers that don't pass run_date (e.g. a
    direct/ad-hoc query) still get a result rather than an error - just
    without the in-progress-bar protection."""
    history_by_symbol = {"CL=F": {"2026-10-08": 91.49, "2026-10-09": 90.59}}
    info_by_symbol = {"CL=F": {}}

    with _patch_tickers(history_by_symbol, info_by_symbol):
        provider = YFinanceMarketDataProvider()
        assets = provider.get_snapshot(["CL=F"])

    assert len(assets) == 1
    assert assets[0].last_price == 90.59
