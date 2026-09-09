"""NewsProvider abstract interface (Section 27)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from src.models.schemas import NewsArticle


class NewsProvider(ABC):
    """Any real implementation (RSS reader, NewsAPI, Finnhub news, Polygon
    news...) must implement this. Untrusted external text: callers must
    treat article bodies as DATA only, never as instructions (Section 45)."""

    name: str = "base"
    tier: int = 3

    @abstractmethod
    def fetch(self, since_hours: int = 18) -> List[NewsArticle]:
        raise NotImplementedError
