"""V2 Part 32: automated validation checks run right before the report is
finalized. Where a violation is auto-fixable (drop the offending item), it
is fixed and logged; where it can only be flagged, it's added to
DataQualityStatus.warnings so the reader sees the caveat rather than a
silently "clean-looking" report.

Not every one of the 32 spec checks is implemented as literal code - a few
(CHECK 11 "no unexplained jargon", CHECK 13 "not repetitive") require
actual language understanding to do well and are left as an editorial
concern for the LLM prompts (see GUARDRAIL_PREAMBLE / task instructions)
rather than a mechanical check. What's implemented here is everything that
can be verified mechanically and cheaply.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from src.models.schemas import ImportanceLevel, MarketSnapshot, StoryAnalysis, TradeIdea


def check_no_nan_displayed(snapshot: MarketSnapshot) -> List[str]:
    """CHECK 1. Belt-and-suspenders: MarketAsset already coerces NaN/inf to
    None at the Pydantic level, so this should never fire - if it does, it
    means some code path bypassed model validation (e.g. mutated a field
    post-construction), which is itself worth surfacing loudly."""
    problems = []
    for asset in snapshot.assets:
        for field_name in ("daily_pct", "last_price", "previous_close", "return_5d_pct"):
            v = getattr(asset, field_name, None)
            if v is not None and isinstance(v, float) and math.isnan(v):
                problems.append(f"{asset.symbol}.{field_name} 出现 NaN，本不应该发生")
    return problems


def enforce_no_low_importance_in_top_stories(stories: List[StoryAnalysis]) -> Tuple[List[StoryAnalysis], List[str]]:
    """CHECK 4: a LOW-importance story should not occupy a Top Stories slot
    even if the deterministic pre-filter let its cluster through (e.g. a
    borderline score). Drops rather than just warns, since Top Stories is
    explicitly meant to be exception-based / high-signal-only."""
    kept, dropped = [], []
    for s in stories:
        if s.importance == ImportanceLevel.LOW:
            dropped.append(s.title)
        else:
            kept.append(s)
    warnings = [f"已从「隔夜真正重要的事」中移除低重要性条目：{t}" for t in dropped]
    return kept, warnings


def enforce_trade_idea_requirements(ideas: List[TradeIdea]) -> Tuple[List[TradeIdea], List[str]]:
    """CHECK 7/8: a directional (LONG WATCH / SHORT WATCH) idea must have
    both an invalidation_condition and an edge_or_mispricing - if either is
    missing, downgrade the idea to WAIT rather than dropping it outright
    (the underlying analysis may still be useful context), and record why."""
    from src.models.schemas import TradeDirection

    warnings: List[str] = []
    directional = {TradeDirection.LONG_WATCH, TradeDirection.SHORT_WATCH}
    out: List[TradeIdea] = []
    for idea in ideas:
        if idea.direction in directional:
            missing = []
            if not idea.invalidation_condition:
                missing.append("失效条件（invalidation_condition）")
            if not idea.edge_or_mispricing:
                missing.append("市场可能错在哪里（edge_or_mispricing）")
            if missing:
                warnings.append(
                    f"{idea.ticker or '未命名标的'} 缺少{'/'.join(missing)}，已降级为 WAIT"
                )
                idea.direction = TradeDirection.WAIT
        out.append(idea)
    return out, warnings


def run_v2_validation(
    snapshot: MarketSnapshot,
    top_stories: List[StoryAnalysis],
    trade_ideas: List[TradeIdea],
) -> Tuple[List[StoryAnalysis], List[TradeIdea], List[str]]:
    """Runs the mechanically-checkable subset of Part 32 and returns the
    (possibly modified) top_stories/trade_ideas plus a flat warnings list
    to fold into DataQualityStatus."""
    all_warnings: List[str] = []

    nan_problems = check_no_nan_displayed(snapshot)
    all_warnings.extend(nan_problems)

    top_stories, dropped_warnings = enforce_no_low_importance_in_top_stories(top_stories)
    all_warnings.extend(dropped_warnings)

    trade_ideas, downgrade_warnings = enforce_trade_idea_requirements(trade_ideas)
    all_warnings.extend(downgrade_warnings)

    return top_stories, trade_ideas, all_warnings
