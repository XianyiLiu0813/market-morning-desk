"""What Changed Overnight (V2 Part 5-6).

Deterministic diff against yesterday's persisted state - NOT an LLM call.
Trading is often driven by changes in expectations/regime, not the
absolute level, so this compares:
  - today's ThemeView.structural_view/tactical_view vs yesterday's
    persisted theme_daily_views row for the same theme_key
  - today's regime labels vs yesterday's persisted regime
  - today's Trader's Dashboard rates/USD/volatility vs simple thresholds
    (large bp/percent moves are "changes" worth flagging even without a
    stored yesterday snapshot, since the move itself is the change)

Reads directly from the SQLite tables written by pipeline.py on the
previous run - if there is no prior day's data (first run, or a gap),
each comparison degrades to "no baseline available" and is simply
omitted, never fabricated.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select

from src.models.database import AnalysisResultRow, ThemeDailyViewRow, get_session
from src.models.schemas import MarketSnapshot, ThemeView, TraderDashboard


def _get_yesterday_theme_views(run_date: date) -> Dict[str, ThemeDailyViewRow]:
    yesterday = run_date - timedelta(days=1)
    with get_session() as session:
        rows = session.execute(
            select(ThemeDailyViewRow).where(ThemeDailyViewRow.run_date == yesterday)
        ).scalars().all()
        # Detach values needed after session closes.
        return {
            r.theme_key: ThemeDailyViewRow(
                theme_key=r.theme_key,
                structural_view=r.structural_view,
                tactical_view=r.tactical_view,
                momentum=r.momentum,
            )
            for r in rows
        }


def _get_yesterday_regime(run_date: date) -> Optional[dict]:
    yesterday = run_date - timedelta(days=1)
    with get_session() as session:
        row = session.execute(
            select(AnalysisResultRow)
            .where(AnalysisResultRow.run_date == yesterday, AnalysisResultRow.kind == "regime")
            .order_by(AnalysisResultRow.id.desc())
        ).scalars().first()
        if row is None:
            return None
        try:
            return json.loads(row.payload_json)
        except (json.JSONDecodeError, TypeError):
            return None


_SENTIMENT_RANK = {
    "BEARISH": -2, "SLIGHTLY_BEARISH": -1, "NEUTRAL": 0,
    "SLIGHTLY_BULLISH": 1, "BULLISH": 2,
}


def _theme_change_label(theme_key: str, theme_name: str, today: ThemeView, yesterday_row: Optional[ThemeDailyViewRow]) -> Optional[str]:
    if yesterday_row is None:
        return None
    today_structural = today.structural_view.value
    today_tactical = today.tactical_view.value
    y_structural = yesterday_row.structural_view
    y_tactical = yesterday_row.tactical_view

    struct_delta = _SENTIMENT_RANK.get(today_structural, 0) - _SENTIMENT_RANK.get(y_structural, 0)
    tactical_delta = _SENTIMENT_RANK.get(today_tactical, 0) - _SENTIMENT_RANK.get(y_tactical, 0)

    if struct_delta == 0 and tactical_delta == 0:
        return None  # no meaningful change - exception-based reporting drops this row

    arrow = "↑" if (struct_delta + tactical_delta) > 0 else "↓"
    parts = []
    if struct_delta != 0:
        parts.append(f"结构性判断{'上修' if struct_delta > 0 else '下修'}")
    if tactical_delta != 0:
        parts.append(f"战术性判断{'转多' if tactical_delta > 0 else '转空'}")
    return f"{theme_name} {arrow} " + "、".join(parts)


def apply_theme_changes(run_date: date, theme_views: List[ThemeView]) -> List[str]:
    """Sets ThemeView.change_vs_yesterday on each theme (so
    ThemeView.is_meaningful_change - Part 8 exception-based reporting - is
    driven by an actual day-over-day diff, not just "has some evidence")
    and returns the same labels as a flat list for the top-level What
    Changed Overnight bullets."""
    yesterday_map = _get_yesterday_theme_views(run_date)
    out: List[str] = []
    for tv in theme_views:
        label = _theme_change_label(tv.theme_key, tv.theme_name, tv, yesterday_map.get(tv.theme_key))
        tv.change_vs_yesterday = label
        if label:
            out.append(label)
    return out


def detect_regime_change(run_date: date, today_labels: List[str], today_summary: str) -> Optional[str]:
    yesterday = _get_yesterday_regime(run_date)
    if yesterday is None:
        return None
    y_labels = set(yesterday.get("labels", []))
    t_labels = set(today_labels)
    if y_labels == t_labels:
        return None
    added = t_labels - y_labels
    removed = y_labels - t_labels
    bits = []
    if added:
        bits.append(f"新增：{', '.join(sorted(added))}")
    if removed:
        bits.append(f"消退：{', '.join(sorted(removed))}")
    return "市场状态 → " + "；".join(bits)


def detect_dashboard_changes(dashboard: TraderDashboard, snapshot: MarketSnapshot) -> List[str]:
    """Flag dimensions whose underlying move itself is large enough to be
    "the change" today, even without a stored prior-day dashboard - e.g. a
    >=5bp move in the 10Y or a VIX move >=8% is newsworthy on its own."""
    out: List[str] = []
    us10y = snapshot.get("US10Y")
    if us10y is not None and us10y.bp_change is not None and abs(us10y.bp_change) >= 5:
        direction = "更偏鹰（收益率上行）" if us10y.bp_change > 0 else "更偏鸽（收益率下行）"
        out.append(f"利率 {'↑' if us10y.bp_change > 0 else '↓'} {direction}，US10Y {us10y.bp_change:+.1f}bp")
    vix = snapshot.get("^VIX")
    if vix is not None and vix.daily_pct is not None and abs(vix.daily_pct) >= 8:
        direction = "波动率明显上升" if vix.daily_pct > 0 else "波动率明显回落"
        out.append(f"VIX {'↑' if vix.daily_pct > 0 else '↓'} {direction}（{vix.daily_pct:+.2f}%）")
    dxy = snapshot.get("DXY")
    if dxy is not None and dxy.daily_pct is not None and abs(dxy.daily_pct) >= 0.5:
        direction = "美元走强" if dxy.daily_pct > 0 else "美元走弱"
        out.append(f"美元 {'↑' if dxy.daily_pct > 0 else '↓'} {direction}（DXY {dxy.daily_pct:+.2f}%）")
    return out


def build_what_changed_overnight(
    run_date: date,
    theme_views: List[ThemeView],
    regime_labels: List[str],
    regime_summary: str,
    dashboard: Optional[TraderDashboard],
    snapshot: MarketSnapshot,
) -> List[str]:
    changes: List[str] = []
    regime_change = detect_regime_change(run_date, regime_labels, regime_summary)
    if regime_change:
        changes.append(regime_change)
    changes.extend(apply_theme_changes(run_date, theme_views))
    if dashboard is not None:
        changes.extend(detect_dashboard_changes(dashboard, snapshot))
    return changes
