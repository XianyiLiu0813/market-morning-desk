"""Pre-send data quality gate (Section 34; V2 Part 2 - the P0 gate).

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


def check_core_assets(snapshot: MarketSnapshot, settings: Settings) -> List[str]:
    """Return the list of core-required symbols (Part 2) that are missing,
    NaN/None, or stale in the validated snapshot. Called separately from
    run_quality_checks so collectors/market.py can also surface this list
    directly on the snapshot for downstream modules to see at a glance."""
    core_symbols = settings.quality.get("core_required_assets", [])
    by_symbol = {a.symbol: a for a in snapshot.assets}
    missing: List[str] = []
    for sym in core_symbols:
        asset = by_symbol.get(sym)
        if asset is None:
            missing.append(sym)
            continue
        if asset.is_stale:
            missing.append(sym)
            continue
        # A rate asset only needs a valid level; a normal asset needs a
        # valid daily_pct. Pydantic already turned any NaN into None, so a
        # plain None check here is sufficient - no isnan() needed twice.
        if asset.is_rate:
            if asset.last_price is None:
                missing.append(sym)
        elif asset.daily_pct is None and asset.last_price is None:
            missing.append(sym)
    return missing


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

    core_missing = check_core_assets(snapshot, settings)
    max_core_missing = settings.quality.get("max_core_assets_missing", 3)
    if core_missing:
        warnings.append(f"以下核心资产数据暂缺或已过期：{', '.join(core_missing)}。")
    if len(core_missing) > max_core_missing:
        reasons.append(
            f"核心资产数据缺失过多（{len(core_missing)} / {max_core_missing} 上限）："
            f"{', '.join(core_missing)}。"
        )

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
        core_assets_missing=core_missing,
    )
