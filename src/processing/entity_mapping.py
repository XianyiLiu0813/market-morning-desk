"""Rule-based ticker/theme mapping (Section 9 step: entity extraction /
ticker-theme mapping).

Deliberately NOT an LLM step: mapping raw text to tickers/themes via
keyword and ticker-list matching is deterministic, auditable, and free of
hallucination risk. The LLM is reserved for judgment calls (why something
matters, what it implies) rather than fact extraction that a lookup table
already solves reliably.
"""
from __future__ import annotations

import re
from typing import Dict, List, Pattern, Tuple

from src.models.schemas import NewsArticle
from src.utils.config import Settings


def _word_boundary_pattern(term: str) -> Pattern[str]:
    """Compile a case-insensitive, word-boundary-anchored pattern for `term`.

    Plain substring matching is unsafe for short tickers: naive `in` checks
    would match "MU" inside "monopoly", "F" inside almost anything, "C"
    inside "China", etc. \\b anchors only match where a word character
    meets a non-word character, so "MU" matches "MU reported ..." but not
    "monopoly" or "immune".
    """
    return re.compile(r"\b" + re.escape(term.lower()) + r"\b")


def build_keyword_index(settings: Settings) -> Dict[str, List[Pattern[str]]]:
    """theme_key -> compiled keyword/ticker patterns (word-boundary safe)."""
    index: Dict[str, List[Pattern[str]]] = {}
    for theme in settings.themes:
        terms = list(theme.get("keywords", [])) + list(theme.get("tickers", []))
        index[theme["key"]] = [_word_boundary_pattern(t) for t in terms if t]
    return index


def build_ticker_index(settings: Settings) -> List[Tuple[str, Pattern[str]]]:
    """List of (ticker, compiled pattern-for-its-bare-symbol). HK-style
    tickers like "9988.HK" are matched on the bare numeric/alpha part only
    - the ".HK" suffix essentially never appears verbatim in English prose,
    so matching just the bare part (still word-boundary anchored) is the
    practical choice; a false positive on a 4+ digit HK stock code inside
    ordinary text is rare enough to accept for V1."""
    out: List[Tuple[str, Pattern[str]]] = []
    for group in settings.watchlist.values():
        for entry in group:
            ticker = entry["ticker"]
            bare = ticker.split(".")[0]
            if not bare:
                continue
            out.append((ticker, _word_boundary_pattern(bare)))
    return out


def enrich_article(
    article: NewsArticle,
    keyword_index: Dict[str, List[Pattern[str]]],
    ticker_index: List[Tuple[str, Pattern[str]]],
) -> NewsArticle:
    """Fill in / augment tickers and themes on an article using keyword and
    watchlist matching. Existing values from the provider are kept and
    de-duplicated against, never overwritten."""
    text = " ".join(
        filter(None, [article.title, article.summary or "", article.body_excerpt or ""])
    ).lower()

    matched_themes = set(article.themes)
    for theme_key, patterns in keyword_index.items():
        if any(p.search(text) for p in patterns):
            matched_themes.add(theme_key)

    matched_tickers = set(article.tickers)
    for ticker, pattern in ticker_index:
        if pattern.search(text):
            matched_tickers.add(ticker)

    article.themes = sorted(matched_themes)
    article.tickers = sorted(matched_tickers)
    return article


def enrich_all(articles: List[NewsArticle], settings: Settings) -> List[NewsArticle]:
    keyword_index = build_keyword_index(settings)
    ticker_index = build_ticker_index(settings)
    return [enrich_article(a, keyword_index, ticker_index) for a in articles]
