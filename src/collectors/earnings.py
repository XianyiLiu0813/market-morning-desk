"""Earnings calendar / earnings-release collector - placeholder interface.

A real implementation would use a vendor's earnings-calendar endpoint
(Finnhub, Alpha Vantage, Polygon all offer one) keyed by FINNHUB_API_KEY /
ALPHAVANTAGE_API_KEY / POLYGON_API_KEY. Kept minimal in V1: company
earnings-related news still flows through the generic NewsProvider
pipeline (tagged via entity_mapping.py), this module is for a dedicated
"upcoming earnings" list to eventually feed the risk calendar.
"""
from __future__ import annotations

from datetime import date
from typing import List

from src.models.schemas import MacroEvent


class EarningsCalendarProvider:
    name = "base"

    def get_upcoming(self, run_date: date, tickers: List[str]) -> List[MacroEvent]:
        return []
