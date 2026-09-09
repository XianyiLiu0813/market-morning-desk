"""Real NewsProvider implementations: RSS feeds (feedparser) + generic search
APIs (NewsAPI.org / Finnhub / Polygon, if keys are configured).

RSS is used for Tier-2/3 sources listed with kind: rss in
config/sources.yaml - no API key required, and it's a "permitted access"
mechanism per Section 8 (avoids fragile unauthorized scraping).
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from src.models.schemas import NewsArticle, SourceTier
from src.providers.news_base import NewsProvider
from src.utils.retry import retry_with_backoff

logger = logging.getLogger("morning_desk")


def _article_id(source_id: str, url: str, title: str) -> str:
    """Include source_id in the hash so the SAME underlying story carried by
    two different feeds (e.g. it appears in both a publisher's main feed and
    its "world" feed, or is picked up by two different outlets) gets two
    distinct raw-record IDs - each source's copy is a legitimate distinct
    source_record, and news_articles.article_id is a unique key across all
    of them. Clustering (story_clustering.py) is what merges these into one
    story for the report; it works on title/ticker similarity, not on
    article_id, so this change doesn't affect deduplication behavior."""
    return hashlib.sha1(f"{source_id}|{url}|{title}".encode("utf-8")).hexdigest()[:16]


class RssNewsProvider(NewsProvider):
    """Generic RSS/Atom feed reader. One instance per feed URL."""

    def __init__(self, source_id: str, source_name: str, feed_url: str, tier: int = 2):
        self.name = f"rss:{source_id}"
        self.tier = tier
        self.source_id = source_id
        self.source_name = source_name
        self.feed_url = feed_url

    @retry_with_backoff(max_attempts=3)
    def fetch(self, since_hours: int = 18) -> List[NewsArticle]:
        import feedparser

        feed = feedparser.parse(self.feed_url)
        if getattr(feed, "bozo", False) and not feed.entries:
            raise RuntimeError(f"Failed to parse feed: {self.feed_url}")

        cutoff = datetime.now(tz=timezone.utc).timestamp() - since_hours * 3600
        out: List[NewsArticle] = []
        for entry in feed.entries:
            published: Optional[datetime] = None
            if getattr(entry, "published_parsed", None):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if published and published.timestamp() < cutoff:
                continue
            title = getattr(entry, "title", "").strip()
            if not title:
                continue
            url = getattr(entry, "link", None)
            out.append(
                NewsArticle(
                    article_id=_article_id(self.source_id, url or title, title),
                    title=title,
                    summary=getattr(entry, "summary", None),
                    body_excerpt=None,
                    url=url,
                    source_id=self.source_id,
                    source_name=self.source_name,
                    tier=SourceTier(self.tier),
                    published_at=published,
                    tickers=[],
                    themes=[],
                )
            )
        return out


class NewsApiProvider(NewsProvider):
    """NewsAPI.org search-based provider. Requires NEWSAPI_KEY."""

    name = "newsapi"
    tier = 2

    def __init__(self, api_key: str, query: str = "markets OR Fed OR earnings OR semiconductor"):
        self.api_key = api_key
        self.query = query

    @retry_with_backoff(max_attempts=3)
    def fetch(self, since_hours: int = 18) -> List[NewsArticle]:
        import requests

        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": self.query,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 30,
                "apiKey": self.api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        out: List[NewsArticle] = []
        for item in data.get("articles", []):
            title = (item.get("title") or "").strip()
            if not title:
                continue
            url = item.get("url")
            published_at = None
            if item.get("publishedAt"):
                published_at = datetime.fromisoformat(item["publishedAt"].replace("Z", "+00:00"))
            source_name = (item.get("source") or {}).get("name", "NewsAPI")
            out.append(
                NewsArticle(
                    article_id=_article_id("newsapi", url or title, title),
                    title=title,
                    summary=item.get("description"),
                    body_excerpt=item.get("content"),
                    url=url,
                    source_id="newsapi",
                    source_name=source_name,
                    tier=SourceTier(3),
                    published_at=published_at,
                    tickers=[],
                    themes=[],
                )
            )
        return out
