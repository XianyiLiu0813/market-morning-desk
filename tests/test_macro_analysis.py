"""Macro-vs-market cluster routing tests (src/analysis/macro_analysis.py).

The oil/geopolitical-conflict keywords were added after a real miss: an
Iran/Hormuz tanker-attack oil-price shock (one of the two biggest market
movers of its session) had no match in config/themes.yaml (entirely
AI-investing-themed by design) and fell into the company/theme-scored
"market" bucket instead of "macro", where it was structurally
disadvantaged against AI-theme stories and never surfaced."""
from __future__ import annotations

from src.analysis.macro_analysis import is_macro_cluster, split_macro_vs_market
from src.models.schemas import NewsCluster


def _cluster(title: str, tickers=None) -> NewsCluster:
    return NewsCluster(
        cluster_id=title, representative_article_id="a1", member_article_ids=["a1"],
        title=title, tickers=tickers or [], urls=["https://example.com"], best_tier=2,
    )


def test_oil_tanker_attack_story_routes_to_macro():
    c = _cluster("Oil prices jump as Iran steps up tanker attacks, hurricane threatens U.S. Gulf production")
    assert is_macro_cluster(c) is True


def test_opec_and_hormuz_phrases_route_to_macro():
    assert is_macro_cluster(_cluster("OPEC+ weighs output amid Strait of Hormuz tensions")) is True
    assert is_macro_cluster(_cluster("Brent crude surges on Gulf shipping disruption")) is True


def test_unrelated_company_named_oil_dri_not_misrouted():
    """"Oil-Dri Corporation" mentions "oil" but is a routine earnings
    release, not a macro/geopolitical story - must not be misrouted by an
    over-broad bare "oil" keyword."""
    c = _cluster("Oil Dri GAAP EPS of $1.00, revenue of $129.29M")
    assert is_macro_cluster(c) is False


def test_split_puts_oil_shock_in_macro_bucket_not_market():
    oil_story = _cluster("Oil prices jump as Iran steps up tanker attacks, hurricane threatens U.S. Gulf production")
    company_story = _cluster("Micron, Nvidia and AI chip stocks fall as report on OpenAI's revenue causes concern", tickers=["MU", "NVDA"])
    macro, market = split_macro_vs_market([oil_story, company_story])
    assert oil_story in macro
    assert company_story in market
