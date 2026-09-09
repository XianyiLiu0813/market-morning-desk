"""Pre-send data quality gate (Section 34).

Runs right before rendering/sending. If quality is below the minimum bar,
the report is still generated but clearly labeled DATA QUALITY WARNING /
degraded mode, rather than silently sending a misleadingly "normal"-looking
report.
"""
from __future__ import annotations

from typing import List

from src.models.schemas import (
    DataQualityStatus,
    MarketSnapshot,
    NewsCluster,
    StoryAnalysis,
)
from src.utils.config import Settings


def run_quality_checks(
    snapshot: MarketSnapshot,
    clusters: List[NewsCluster],
    story_analyses: List[StoryAnalysis],
    settings: Settings,
) -> DataQualityStatus:
    warnings: List[str] = list(snapshot.warnings)
    reasons: List[str] = []

    min_assets = settings.quality.get("require_min_market_assets", 5)
    if len(snapshot.assets) < min_assets:
        reasons.append(
            f"Market data coverage below minimum ({len(snapshot.assets)} < {min_assets})."
        )

    stale = [a for a in snapshot.assets if a.is_stale]
    if len(stale) > len(snapshot.assets) / 2 and snapshot.assets:
        reasons.append("More than half of market assets have stale data.")

    if settings.quality.get("require_source_url", True):
        missing_url = [c for c in clusters if not c.urls]
        if missing_url:
            warnings.append(
                f"{len(missing_url)} story cluster(s) are missing a source URL (down-weighted, not dropped)."
            )

    if not clusters:
        reasons.append("No news clusters were produced - news pipeline may have failed entirely.")

    if story_analyses:
        no_source = [s for s in story_analyses if not s.source_ids]
        if no_source:
            reasons.append(
                f"{len(no_source)} story analysis object(s) are missing source_ids (traceability requirement, Section 6/26)."
            )

    degraded = len(reasons) > 0
    return DataQualityStatus(
        ok=not degraded,
        warnings=warnings,
        degraded_mode=degraded,
        reasons=reasons,
    )
