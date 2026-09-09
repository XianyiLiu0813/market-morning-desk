"""HKEX company announcements collector - placeholder interface (Section 38).

HKEX (https://www1.hkexnews.hk) does not offer a public, terms-friendly
bulk API for company announcements. Building a scraper against their
website would be brittle and could violate their terms of use, so V1
ships a clean interface + a documented no-op implementation instead of a
fragile scraper. Swap in a licensed data vendor (e.g. a HKEX-authorized
redistributor) by implementing HkexAnnouncementsProvider.fetch() - the rest
of the Morning Desk (scoring, clustering, report rendering) needs no
changes when this is filled in.
"""
from __future__ import annotations

from typing import List

from src.models.schemas import NewsArticle
from src.providers.news_base import NewsProvider


class HkexAnnouncementsProvider(NewsProvider):
    name = "hkex_announcements"
    tier = 1

    def __init__(self, tickers: List[str]):
        self.tickers = tickers

    def fetch(self, since_hours: int = 18) -> List[NewsArticle]:
        # Intentionally returns empty in V1. See module docstring: replace
        # with a licensed data vendor implementation when available. The
        # rest of the Morning Desk continues functioning without it
        # (Section 39: "the rest of the Morning Desk must continue
        # functioning").
        return []
