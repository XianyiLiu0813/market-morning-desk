"""Cluster articles reporting the same underlying event (Section 9).

Approach: group articles whose normalized titles are highly similar
(difflib ratio) OR that share >=2 tickers and were published within a
tight time window. This is intentionally simple/transparent for V1 rather
than embedding-based clustering, per Section 37 (don't overengineer V1).
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import List

from datetime import datetime, timezone

from src.models.schemas import NewsArticle, NewsCluster, ImportanceScore
from src.processing.normalize import normalize_title

TITLE_SIMILARITY_THRESHOLD = 0.55


def _title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def cluster_articles(articles: List[NewsArticle]) -> List[NewsCluster]:
    # Sort so the earliest-published (often the primary source) becomes the
    # cluster representative when it's also the highest-tier source.
    _epoch = datetime.min.replace(tzinfo=timezone.utc)

    def _sort_key(a: NewsArticle):
        published = a.published_at or _epoch
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return (a.tier.value, published)

    sorted_articles = sorted(articles, key=_sort_key)

    clusters: List[List[NewsArticle]] = []
    for art in sorted_articles:
        placed = False
        for cluster in clusters:
            rep = cluster[0]
            same_event = _title_similarity(art.title, rep.title) >= TITLE_SIMILARITY_THRESHOLD
            shared_tickers = set(art.tickers) & set(rep.tickers)
            if same_event or (len(shared_tickers) >= 2 and len(art.tickers) > 0):
                cluster.append(art)
                placed = True
                break
        if not placed:
            clusters.append([art])

    out: List[NewsCluster] = []
    for cluster in clusters:
        # Prefer the highest-tier (lowest tier number) article as representative;
        # ties broken by earliest publish time.
        rep = sorted(cluster, key=_sort_key)[0]
        tickers = sorted({t for a in cluster for t in a.tickers})
        themes = sorted({t for a in cluster for t in a.themes})
        now = datetime.now(tz=timezone.utc)
        rep_published = rep.published_at or now
        if rep_published.tzinfo is None:
            rep_published = rep_published.replace(tzinfo=timezone.utc)
        hours_since = max(0.0, (now - rep_published).total_seconds() / 3600.0)
        fact_hint = rep.summary or rep.body_excerpt or rep.title
        # Build source_id -> (name, tier) once so source_ids/source_names/
        # source_tiers stay correctly aligned by key, not by sort order.
        source_info = {a.source_id: (a.source_name, a.tier.value) for a in cluster}
        sorted_source_ids = sorted(source_info.keys())
        out.append(
            NewsCluster(
                cluster_id=f"cl_{rep.article_id}",
                representative_article_id=rep.article_id,
                member_article_ids=[a.article_id for a in cluster],
                title=rep.title,
                tickers=tickers,
                themes=themes,
                importance=ImportanceScore(),
                source_ids=sorted_source_ids,
                source_names=[source_info[sid][0] for sid in sorted_source_ids],
                source_tiers={sid: source_info[sid][1] for sid in sorted_source_ids},
                urls=[a.url for a in cluster if a.url],
                best_tier=min(a.tier.value for a in cluster),
                fact_hint=fact_hint,
                hours_since_publish=round(hours_since, 1),
                # V2 Part 11 classification QA: keyword-based tagging that
                # fires on 4+ unrelated themes for one cluster is a red flag
                # (e.g. a story spuriously matching both "Gold" and
                # "Software/SaaS" keywords) rather than genuinely
                # multi-theme news. Excluded from theme/company analysis
                # until reviewed, rather than silently mis-filed.
                unclassified=len(themes) >= 4,
            )
        )
    return out
