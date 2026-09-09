"""Market data collection orchestration.

Wraps whichever MarketDataProvider is configured (mock or real) and applies
the data-quality checks from Section 34 (freshness, minimum asset count).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Tuple

from src.models.schemas import MarketAsset, MarketSnapshot
from src.providers.market_base import MarketDataProvider
from src.utils.config import Settings
from src.utils.time import age_minutes, now_sgt, now_utc

logger = logging.getLogger("morning_desk")


def flatten_asset_symbols(settings: Settings) -> List[Tuple[str, str, str]]:
    """Return (symbol, display_name, group) tuples from config/assets.yaml."""
    out = []
    for group in settings.asset_groups:
        for asset in group.get("assets", []):
            out.append((asset["symbol"], asset["display"], group["group"]))
    return out


def collect_market_snapshot(
    provider: MarketDataProvider, settings: Settings, run_date: date
) -> MarketSnapshot:
    asset_defs = flatten_asset_symbols(settings)
    symbols = [s for s, _, _ in asset_defs]

    warnings: List[str] = []
    try:
        assets = provider.get_snapshot(symbols)
    except Exception as exc:  # noqa: BLE001
        logger.error("Market data provider %s failed entirely: %s", provider.name, exc)
        assets = []
        warnings.append(f"行情数据源 '{provider.name}' 完全失败：{exc}")

    # Backfill group/display metadata in case a provider only returns bare
    # price data keyed by symbol.
    meta_by_symbol = {s: (d, g) for s, d, g in asset_defs}
    for asset in assets:
        if asset.symbol in meta_by_symbol:
            display, group = meta_by_symbol[asset.symbol]
            asset.display_name = asset.display_name or display
            asset.group = asset.group or group

    max_age = settings.quality.get("max_market_data_age_minutes", 240)
    for asset in assets:
        if asset.as_of is not None and age_minutes(asset.as_of) > max_age:
            asset.is_stale = True

    stale_count = sum(1 for a in assets if a.is_stale)
    if stale_count:
        warnings.append(f"有 {stale_count} 项行情数据已超过 {max_age} 分钟未更新")

    min_assets = settings.quality.get("require_min_market_assets", 5)
    got_symbols = {a.symbol for a in assets}
    missing = [s for s in symbols if s not in got_symbols]
    if missing:
        logger.warning("Market data missing for %d symbol(s): %s", len(missing), ", ".join(missing))
    if len(assets) < min_assets:
        warnings.append(
            f"只获取到 {len(assets)} 项行情数据（最低要求 {min_assets} 项）"
        )

    return MarketSnapshot(
        run_date=run_date,
        generated_at=now_utc(),
        assets=assets,
        warnings=warnings,
    )
