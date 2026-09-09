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
            f"行情数据覆盖不足最低要求（当前 {len(snapshot.assets)} 个，最低要求 {min_assets} 个）。"
        )

    stale = [a for a in snapshot.assets if a.is_stale]
    if len(stale) > len(snapshot.assets) / 2 and snapshot.assets:
        reasons.append("超过一半的行情资产数据已过期（stale）。")

    if settings.quality.get("require_source_url", True):
        missing_url = [c for c in clusters if not c.urls]
        if missing_url:
            warnings.append(
                f"有 {len(missing_url)} 条新闻缺少来源链接（已降权处理，未被丢弃）。"
            )

    if not clusters:
        reasons.append("未生成任何新闻聚类——新闻采集流程可能整体失败了。")

    if story_analyses:
        no_source = [s for s in story_analyses if not s.source_ids]
        if no_source:
            reasons.append(
                f"有 {len(no_source)} 条新闻解读缺少来源标识（source_ids，违反溯源要求）。"
            )

    degraded = len(reasons) > 0
    return DataQualityStatus(
        ok=not degraded,
        warnings=warnings,
        degraded_mode=degraded,
        reasons=reasons,
    )
