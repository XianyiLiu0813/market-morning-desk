"""Importance scoring tests (Section 35)."""
from __future__ import annotations

from src.models.schemas import MarketAsset, NewsCluster
from src.processing.scoring import score_clusters
from src.utils.config import get_settings


def make_cluster(**kwargs) -> NewsCluster:
    defaults = dict(
        cluster_id="c1",
        representative_article_id="a1",
        member_article_ids=["a1"],
        title="Some story",
        tickers=[],
        themes=[],
        source_ids=["src1"],
        source_names=["Source"],
        source_tiers={"src1": 2},
        urls=["https://example.com"],
        best_tier=2,
        fact_hint="fact",
        hours_since_publish=5.0,
    )
    defaults.update(kwargs)
    return NewsCluster(**defaults)


def test_higher_tier_source_scores_higher_source_quality(settings):
    c_primary = make_cluster(cluster_id="c1", best_tier=1)
    c_secondary = make_cluster(cluster_id="c2", best_tier=3)
    scored = score_clusters([c_primary, c_secondary], {}, settings)
    by_id = {c.cluster_id: c for c in scored}
    assert by_id["c1"].importance.source_quality > by_id["c2"].importance.source_quality


def test_theme_relevance_increases_with_matched_themes(settings):
    core_theme_key = settings.themes[0]["key"]
    c_no_theme = make_cluster(cluster_id="c1", themes=[])
    c_with_theme = make_cluster(cluster_id="c2", themes=[core_theme_key])
    scored = score_clusters([c_no_theme, c_with_theme], {}, settings)
    by_id = {c.cluster_id: c for c in scored}
    assert by_id["c2"].importance.theme_relevance > by_id["c1"].importance.theme_relevance


def test_price_confirmation_reflects_actual_market_move(settings):
    assets = {"NVDA": MarketAsset(symbol="NVDA", display_name="NVIDIA", group="", daily_pct=4.5)}
    c = make_cluster(cluster_id="c1", tickers=["NVDA"])
    scored = score_clusters([c], assets, settings)
    assert scored[0].importance.price_confirmation == 5.0


def test_price_confirmation_neutral_when_no_price_data(settings):
    c = make_cluster(cluster_id="c1", tickers=["UNKNOWN"])
    scored = score_clusters([c], {}, settings)
    assert scored[0].importance.price_confirmation == 1.5


def test_clusters_sorted_descending_by_total_score(settings):
    core_theme_key = settings.themes[0]["key"]
    low = make_cluster(cluster_id="low", themes=[], tickers=[])
    high = make_cluster(cluster_id="high", themes=[core_theme_key], tickers=["NVDA"])
    assets = {"NVDA": MarketAsset(symbol="NVDA", display_name="NVIDIA", group="", daily_pct=5.0)}
    scored = score_clusters([low, high], assets, settings)
    assert scored[0].cluster_id == "high"
    assert scored[0].importance.total >= scored[1].importance.total


def test_weights_are_renormalized_when_not_summing_to_one(settings):
    settings.scoring_weights = {"market_impact": 1.0, "source_quality": 1.0}
    c = make_cluster(cluster_id="c1")
    scored = score_clusters([c], {}, settings)
    # Should not raise, and total should still be within 0-5 scale.
    assert 0 <= scored[0].importance.total <= 5
