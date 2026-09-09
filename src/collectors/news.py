"""News collection orchestration: fetch -> normalize -> dedup -> enrich -> cluster.

A single non-critical NewsProvider failing should not crash the run - it is
logged and the pipeline proceeds with whatever other providers returned
(Section 27/33).
"""
from __future__ import annotations

import logging
from typing import List, Tuple

from src.models.schemas import NewsArticle, NewsCluster
from src.processing.deduplicate import drop_exact_duplicates
from src.processing.entity_mapping import enrich_all
from src.processing.normalize import clean_text, truncate
from src.processing.story_clustering import cluster_articles
from src.providers.news_base import NewsProvider
from src.utils.config import Settings

logger = logging.getLogger("morning_desk")


def collect_articles(providers: List[NewsProvider], since_hours: int = 18) -> List[NewsArticle]:
    all_articles: List[NewsArticle] = []
    for provider in providers:
        try:
            articles = provider.fetch(since_hours=since_hours)
            logger.info("News provider '%s' returned %d article(s)", provider.name, len(articles))
            all_articles.extend(articles)
        except Exception as exc:  # noqa: BLE001
            logger.warning("News provider '%s' failed, skipping: %s", provider.name, exc)
    return all_articles


def normalize_articles(articles: List[NewsArticle]) -> List[NewsArticle]:
    for art in articles:
        art.title = clean_text(art.title)
        art.summary = truncate(art.summary, 400) if art.summary else None
        art.body_excerpt = truncate(art.body_excerpt, 800) if art.body_excerpt else None
    return articles


def process_news_pipeline(
    providers: List[NewsProvider], settings: Settings, since_hours: int = 18
) -> Tuple[List[NewsArticle], List[NewsCluster]]:
    """Full Section-9 pipeline: collection -> normalization -> dedup ->
    entity/theme mapping -> clustering. Scoring happens separately (needs
    the market snapshot). Returns (enriched_articles, clusters) - the raw
    enriched articles are returned too so callers can persist them for
    reproducibility (Section 28: "store raw data so reports are
    reproducible")."""
    raw = collect_articles(providers, since_hours=since_hours)
    raw = normalize_articles(raw)
    deduped = drop_exact_duplicates(raw)
    enriched = enrich_all(deduped, settings)
    clusters = cluster_articles(enriched)
    logger.info(
        "News pipeline: %d raw -> %d after exact-dup removal -> %d clusters",
        len(raw),
        len(deduped),
        len(clusters),
    )
    return enriched, clusters
