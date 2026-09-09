"""Transparent importance scoring (Section 10).

importance_score = weighted sum of 7 sub-scores (0-5 each), weights come
from config/settings.yaml `scoring_weights` (renormalized if they don't sum
to 1.0). This is deliberately rule-based/deterministic - no LLM call - so
the ranking that decides "signal over noise" (Principle 2) is auditable
and testable.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from src.models.schemas import ImportanceScore, MarketAsset, NewsCluster
from src.utils.config import Settings

TIER_SOURCE_QUALITY = {1: 5.0, 2: 3.5, 3: 2.0, 4: 0.5}

DEFAULT_WEIGHTS = {
    "market_impact": 0.25,
    "source_quality": 0.15,
    "novelty": 0.15,
    "theme_relevance": 0.20,
    "company_relevance": 0.10,
    "price_confirmation": 0.10,
    "urgency": 0.05,
}


def _novelty_score(cluster: NewsCluster) -> float:
    """More independent sources covering it = more confirmed. A cluster
    made up of only one source is treated as fresh-but-unconfirmed rather
    than penalized."""
    n_sources = len(cluster.source_ids)
    if n_sources <= 1:
        return 3.5
    if n_sources == 2:
        return 4.2
    return 5.0


def _theme_relevance_score(cluster: NewsCluster, core_theme_keys: set) -> float:
    if not cluster.themes:
        return 0.0
    hits = len(set(cluster.themes) & core_theme_keys)
    return min(5.0, 2.0 + hits * 1.5)


def _company_relevance_score(cluster: NewsCluster, watchlist_tickers: set) -> float:
    hits = len(set(cluster.tickers) & watchlist_tickers)
    if hits == 0:
        return 0.0
    return min(5.0, 2.0 + hits * 1.0)


def _price_confirmation_score(cluster: NewsCluster, assets_by_symbol: Dict[str, MarketAsset]) -> float:
    """Does related market data actually show a move? A story with zero
    price confirmation isn't necessarily unimportant, but confirmed moves
    reduce the risk of chasing a non-event."""
    moves = []
    for ticker in cluster.tickers:
        asset = assets_by_symbol.get(ticker)
        if asset and asset.daily_pct is not None:
            moves.append(abs(asset.daily_pct))
    if not moves:
        return 1.5  # neutral-low: unconfirmed, but not penalized to zero
    max_move = max(moves)
    if max_move >= 3:
        return 5.0
    if max_move >= 1.5:
        return 4.0
    if max_move >= 0.5:
        return 2.5
    return 1.5


def _urgency_score(cluster: NewsCluster) -> float:
    hrs = cluster.hours_since_publish
    if hrs is None:
        return 3.0
    if hrs <= 6:
        return 5.0
    if hrs <= 12:
        return 4.0
    if hrs <= 18:
        return 3.0
    return 2.0


def _market_impact_score(price_confirmation: float, theme_relevance: float) -> float:
    """A blend proxy: real market-moving stories tend to show BOTH theme
    breadth and a confirmed price reaction. This is a simple heuristic, not
    a claim of causality (Principle 4)."""
    return round(min(5.0, 0.5 * price_confirmation + 0.5 * theme_relevance), 2)


def score_clusters(
    clusters: List[NewsCluster],
    assets_by_symbol: Dict[str, MarketAsset],
    settings: Settings,
) -> List[NewsCluster]:
    core_theme_keys = {t["key"] for t in settings.themes}
    watchlist_tickers = {
        entry["ticker"] for group in settings.watchlist.values() for entry in group
    }
    weights = dict(settings.scoring_weights) or dict(DEFAULT_WEIGHTS)
    total_w = sum(weights.values()) or 1.0
    weights = {k: v / total_w for k, v in weights.items()}

    for cluster in clusters:
        source_quality = TIER_SOURCE_QUALITY.get(cluster.best_tier, 2.0)
        novelty = _novelty_score(cluster)
        theme_relevance = _theme_relevance_score(cluster, core_theme_keys)
        company_relevance = _company_relevance_score(cluster, watchlist_tickers)
        price_confirmation = _price_confirmation_score(cluster, assets_by_symbol)
        urgency = _urgency_score(cluster)
        market_impact = _market_impact_score(price_confirmation, theme_relevance)

        score = ImportanceScore(
            market_impact=market_impact,
            source_quality=source_quality,
            novelty=novelty,
            theme_relevance=theme_relevance,
            company_relevance=company_relevance,
            price_confirmation=price_confirmation,
            urgency=urgency,
        )
        total = (
            weights.get("market_impact", 0) * score.market_impact
            + weights.get("source_quality", 0) * score.source_quality
            + weights.get("novelty", 0) * score.novelty
            + weights.get("theme_relevance", 0) * score.theme_relevance
            + weights.get("company_relevance", 0) * score.company_relevance
            + weights.get("price_confirmation", 0) * score.price_confirmation
            + weights.get("urgency", 0) * score.urgency
        )
        score.total = round(total, 3)
        cluster.importance = score

    return sorted(clusters, key=lambda c: c.importance.total, reverse=True)
