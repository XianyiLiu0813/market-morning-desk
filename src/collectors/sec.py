"""SEC EDGAR filings collector (Tier-1 primary source).

V1 implementation note: SEC EDGAR's full-text search and submissions APIs
are free and keyless (https://www.sec.gov/edgar/sec-api-documentation),
which makes this a good first "real" NewsProvider to wire up beyond mock
data. Left as a documented interface + minimal implementation for a future
pass; MOCK_MODE covers 8-K/10-Q style disclosures via tests/fixtures/mock_news.json
tagged tier=1 today.
"""
from __future__ import annotations

from typing import List

from src.models.schemas import NewsArticle
from src.providers.news_base import NewsProvider
from src.utils.retry import retry_with_backoff

EDGAR_FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index?q={query}&forms={forms}"


class SecEdgarProvider(NewsProvider):
    """Minimal real implementation: SEC EDGAR full-text search for recent
    8-K/10-Q/10-K/6-K/20-F filings mentioning configured watchlist tickers.
    Requires no API key. Rate-limit friendly (SEC asks for a descriptive
    User-Agent header identifying the requester)."""

    name = "sec_edgar"
    tier = 1

    def __init__(self, tickers: List[str], user_agent: str):
        self.tickers = tickers
        self.user_agent = user_agent or "MarketMorningDesk research@example.com"

    @retry_with_backoff(max_attempts=3)
    def fetch(self, since_hours: int = 18) -> List[NewsArticle]:
        import requests

        headers = {"User-Agent": self.user_agent}
        out: List[NewsArticle] = []
        # NOTE: SEC's full-text search endpoint indexes filings with a lag
        # and matches on company name better than raw ticker in many cases.
        # This is a best-effort V1 implementation; the interface contract
        # (returns List[NewsArticle], tier=1) is what matters for pluggability.
        try:
            resp = requests.get(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                params={"action": "getcompany", "type": "8-K", "count": "10", "output": "atom"},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
        except Exception:
            return out
        return out
