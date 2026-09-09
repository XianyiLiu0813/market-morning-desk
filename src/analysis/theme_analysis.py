"""Theme/sector analysis (Section 14)."""
from __future__ import annotations

from typing import Dict, List

from src.models.schemas import MarketSnapshot, NewsCluster, ThemeView, ThemeViewList
from src.providers.llm_base import LLMProvider
from src.analysis.llm_client import call_llm_json
from src.utils.config import Settings

TASK = "theme_analysis"

INSTRUCTIONS = """For each theme in INPUT_DATA.themes, assign a view given its related ETF/ticker \
price moves (INPUT_DATA.assets) and any matching news clusters (INPUT_DATA.stories_by_theme).

Return JSON:
{
  "themes": [
    {
      "theme_key": "...",
      "theme_name": "...",
      "view": one of BULLISH, SLIGHTLY_BULLISH, NEUTRAL, SLIGHTLY_BEARISH, BEARISH,
      "momentum": one of IMPROVING, UNCHANGED, DETERIORATING,
      "kind": one of STRUCTURAL, TACTICAL,
      "evidence": ["short evidence bullets citing actual price moves or story facts"],
      "risk": "one concrete counterargument or risk to this view",
      "change_vs_yesterday": "short note or null if unknown",
      "confidence_pct": integer 0-100,
      "source_ids": ["cluster_id strings used"]
    }, ...
  ]
}

Only include a theme if there is at least some price or news evidence for it in INPUT_DATA - \
do not invent a view for a theme with no supporting data; instead omit it or mark NEUTRAL with \
low confidence and evidence noting data was limited."""


def analyze_themes(
    llm: LLMProvider,
    settings: Settings,
    snapshot: MarketSnapshot,
    clusters: List[NewsCluster],
) -> List[ThemeView]:
    assets_by_symbol = {a.symbol: a for a in snapshot.assets}
    themes_payload = []
    for theme in settings.themes:
        etfs = theme.get("related_etfs", [])
        etf_moves = [
            {"symbol": e, "daily_pct": assets_by_symbol[e].daily_pct}
            for e in etfs
            if e in assets_by_symbol
        ]
        matching_clusters = [c for c in clusters if theme["key"] in c.themes]
        if not etf_moves and not matching_clusters:
            continue
        themes_payload.append(
            {
                "key": theme["key"],
                "name": theme["name"],
                "related_etf_moves": etf_moves,
                "matching_stories": [
                    {"cluster_id": c.cluster_id, "title": c.title, "fact_hint": c.fact_hint}
                    for c in matching_clusters[:3]
                ],
                "drivers": theme.get("drivers", []),
                "risks": theme.get("risks", []),
            }
        )

    input_data = {"themes": themes_payload}
    result = call_llm_json(llm, TASK, INSTRUCTIONS, input_data, ThemeViewList)
    if result is not None:
        return result.themes
    return []
