"""News deduplication and clustering tests (Section 35)."""
from __future__ import annotations

from datetime import datetime, timezone

from src.models.schemas import NewsArticle, SourceTier
from src.processing.deduplicate import drop_exact_duplicates
from src.processing.story_clustering import cluster_articles


def make_article(**kwargs) -> NewsArticle:
    defaults = dict(
        article_id="a1",
        title="Some headline",
        summary="summary",
        url="https://example.com/a1",
        source_id="src1",
        source_name="Source One",
        tier=SourceTier.HIGH_QUALITY_MEDIA,
        published_at=datetime.now(tz=timezone.utc),
        tickers=[],
        themes=[],
    )
    defaults.update(kwargs)
    return NewsArticle(**defaults)


def test_drop_exact_duplicates_same_url_same_source():
    a1 = make_article(article_id="a1", url="https://x.com/story", source_id="src1")
    a2 = make_article(article_id="a2", url="https://x.com/story", source_id="src1")
    out = drop_exact_duplicates([a1, a2])
    assert len(out) == 1


def test_drop_exact_duplicates_keeps_cross_source_repeats():
    a1 = make_article(article_id="a1", url="https://x.com/story", source_id="src1")
    a2 = make_article(article_id="a2", url="https://y.com/story", source_id="src2")
    out = drop_exact_duplicates([a1, a2])
    assert len(out) == 2


def test_cluster_articles_merges_same_event_by_title_similarity():
    a1 = make_article(
        article_id="a1",
        title="Hyperscaler raises AI data-center capex guidance for 2027",
        tier=SourceTier.PRIMARY,
    )
    a2 = make_article(
        article_id="a2",
        title="Hyperscaler raises AI data center capex guidance 2027",
        tier=SourceTier.SECONDARY_MEDIA,
    )
    clusters = cluster_articles([a1, a2])
    assert len(clusters) == 1
    assert set(clusters[0].member_article_ids) == {"a1", "a2"}


def test_cluster_articles_merges_by_shared_tickers():
    a1 = make_article(article_id="a1", title="Company X spending update", tickers=["NVDA", "MSFT"])
    a2 = make_article(article_id="a2", title="Totally different headline text here", tickers=["NVDA", "MSFT"])
    clusters = cluster_articles([a1, a2])
    assert len(clusters) == 1


def test_cluster_articles_keeps_unrelated_stories_separate():
    a1 = make_article(article_id="a1", title="Gold rallies to new highs on central bank buying")
    a2 = make_article(article_id="a2", title="Oil prices fall on ample supply outlook", tickers=[])
    clusters = cluster_articles([a1, a2])
    assert len(clusters) == 2


def test_cluster_representative_prefers_primary_tier():
    a1 = make_article(article_id="a1", title="Event happened here today", tier=SourceTier.SECONDARY_MEDIA)
    a2 = make_article(article_id="a2", title="Event happened here today", tier=SourceTier.PRIMARY)
    clusters = cluster_articles([a1, a2])
    assert len(clusters) == 1
    assert clusters[0].representative_article_id == "a2"
    assert clusters[0].best_tier == 1
