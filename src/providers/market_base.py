"""MarketDataProvider abstract interface (Section 27)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional

from src.models.schemas import MarketAsset


class MarketDataProvider(ABC):
    """Any real implementation (yfinance, Polygon, Finnhub, Alpha Vantage...)
    must implement this and return validated MarketAsset objects. Providers
    should raise on total failure but the collector layer decides whether
    that's fatal for the whole run."""

    name: str = "base"

    @abstractmethod
    def get_snapshot(self, symbols: List[str], run_date: Optional[date] = None) -> List[MarketAsset]:
        """Return a MarketAsset for each symbol it could resolve. Missing
        symbols should simply be omitted (not raise) so partial data still
        flows through - the collector logs what's missing.

        run_date is the report's calendar date (SGT) - implementations that
        source from continuously-traded (near-24h) instruments should use
        it to make sure "last"/"previous" land on the session that closed
        before run_date, not a same-day in-progress bar."""
        raise NotImplementedError
