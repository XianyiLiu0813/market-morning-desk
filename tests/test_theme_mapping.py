"""Ticker/theme entity-mapping tests (Section 35)."""
from __future__ import annotations

from datetime import datetime, timezone

from src.models.schemas import NewsArticle, SourceTier
from src.processing.entity_mapping import enrich_all


def make_article(title, summary="", tickers=None, themes=None):
    return NewsArticle(
        article_id="a1",
        title=title,
        summary=summary,
        url="https://example.com",
        source_id="src1",
        source_name="Source",
        tier=SourceTier.HIGH_QUALITY_MEDIA,
        published_at=datetime.now(tz=timezone.utc),
        tickers=tickers or [],
        themes=themes or [],
    )


def test_keyword_match_adds_theme(settings):
    art = make_article("Company discloses new HBM memory pricing trends")
    enriched = enrich_all([art], settings)[0]
    assert "memory_hbm" in enriched.themes


def test_ticker_mention_adds_watchlist_ticker(settings):
    art = make_article("NVDA reports strong quarterly demand for accelerators")
    enriched = enrich_all([art], settings)[0]
    assert "NVDA" in enriched.tickers


def test_company_name_alias_resolves_ticker_without_bare_symbol(settings):
    """Regression: news prose almost always says "Micron"/"Nvidia", never
    the bare ticker - entity mapping must resolve these via name/aliases,
    not just an exact ticker-symbol match (root cause of a real production
    bug where top-scoring stories ended up with tickers=[] and were
    silently dropped downstream)."""
    art = make_article("Micron, Nvidia and AI chip stocks fall as report on OpenAI's revenue causes concern")
    enriched = enrich_all([art], settings)[0]
    assert "MU" in enriched.tickers
    assert "NVDA" in enriched.tickers


def test_company_full_name_phrase_resolves_ticker(settings):
    art = make_article("Micron Technology shares slide after cautious guidance")
    enriched = enrich_all([art], settings)[0]
    assert "MU" in enriched.tickers


def test_unrelated_company_with_similar_word_not_falsely_matched(settings):
    """"Oil-Dri Corporation" mentions "oil" but must not spuriously match
    any watchlist alias/name/ticker."""
    art = make_article("Oil Dri GAAP EPS of $1.00, revenue of $129.29M")
    enriched = enrich_all([art], settings)[0]
    assert enriched.tickers == []


def test_existing_tags_are_preserved_not_overwritten(settings):
    art = make_article("Unrelated headline text", tickers=["MU"], themes=["gold_precious_metals"])
    enriched = enrich_all([art], settings)[0]
    assert "MU" in enriched.tickers
    assert "gold_precious_metals" in enriched.themes


def test_no_false_positive_theme_for_unrelated_text(settings):
    art = make_article("A completely unrelated local weather report for a small town")
    enriched = enrich_all([art], settings)[0]
    assert enriched.themes == []
