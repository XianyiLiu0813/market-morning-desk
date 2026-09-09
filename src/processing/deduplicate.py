"""Exact/near-exact duplicate removal, prior to clustering (Section 9 step 3)."""
from __future__ import annotations

from typing import List

from src.models.schemas import NewsArticle
from src.processing.normalize import normalize_title


def drop_exact_duplicates(articles: List[NewsArticle]) -> List[NewsArticle]:
    """Remove articles with an identical URL or identical normalized title
    from the *same* source (true duplicate fetches, e.g. a feed re-polled).
    Cross-source repeats of the same event are handled by clustering, not
    dropped here, since a Reuters piece and a company 8-K about the same
    event are two independent, still-useful source records."""
    seen = set()
    out: List[NewsArticle] = []
    for art in articles:
        key = (art.url or "", art.source_id, normalize_title(art.title))
        if key in seen:
            continue
        seen.add(key)
        out.append(art)
    return out
