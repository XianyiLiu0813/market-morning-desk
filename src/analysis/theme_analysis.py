"""Theme/sector analysis (Section 14; V2 Part 7-9).

V2 change: a theme now carries INDEPENDENT structural (multi-quarter) and
tactical (days-to-weeks) views, plus a deterministic price_confirmation
read (never LLM-invented - computed in Python from the validated
snapshot before the LLM call, then handed to the LLM as a fact it must
incorporate, not something it decides itself).
"""
from __future__ import annotations

from typing import Dict, List

from src.analysis.llm_client import call_llm_json
from src.analysis.price_check import price_check_for_tickers, summarize_price_confirmation
from src.models.schemas import MarketSnapshot, NewsCluster, ThemeView, ThemeViewList
from src.providers.llm_base import LLMProvider
from src.utils.config import Settings

TASK = "theme_analysis"

INSTRUCTIONS = """For each theme in INPUT_DATA.themes, assign TWO independent views:

- structural_view: the multi-quarter/multi-year industry or earnings trend. Does NOT change just \
because of one day's price action.
- tactical_view: whether, at TODAY'S price/sentiment/catalyst, this theme is worth trading in the \
next few days to weeks. A great structural theme can still have tactical_view = NEUTRAL if price \
confirmation is weak or the theme looks crowded/already-priced-in.

INPUT_DATA.themes[].price_confirmation is a DETERMINISTIC pre-computed read ("确认"=confirmed, \
"背离"=diverging from the claimed view, "分化"=mixed/dispersed, "中性"=neutral, "数据不足"=insufficient \
data) - you MUST treat this as ground truth and factor it into tactical_view (e.g. do not set \
tactical_view=BULLISH if price_confirmation="背离"), never contradict or re-derive it yourself.

Return JSON:
{
  "themes": [
    {
      "theme_key": "...",
      "theme_name": "...",
      "structural_view": one of BULLISH, SLIGHTLY_BULLISH, NEUTRAL, SLIGHTLY_BEARISH, BEARISH,
      "tactical_view": one of BULLISH, SLIGHTLY_BULLISH, NEUTRAL, SLIGHTLY_BEARISH, BEARISH,
      "momentum": one of IMPROVING, UNCHANGED, DETERIORATING,
      "structural_reason": "1 short sentence: the multi-quarter thesis",
      "tactical_reason": "1 short sentence: why trade-worthy or not RIGHT NOW",
      "price_confirmation": "copy exactly from INPUT_DATA.themes[].price_confirmation",
      "evidence": ["short evidence bullets citing actual price moves or story facts"],
      "risk": "one concrete counterargument or risk to the structural view",
      "confidence_pct": integer 0-100,
      "source_ids": ["cluster_id strings used"]
    }, ...
  ]
}

Only include a theme if there is at least some price or news evidence for it in INPUT_DATA - \
do not invent a view for a theme with no supporting data."""


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
            if e in assets_by_symbol and assets_by_symbol[e].daily_pct is not None
        ]
        matching_clusters = [c for c in clusters if theme["key"] in c.themes and not c.unclassified]
        if not etf_moves and not matching_clusters:
            continue

        # Deterministic price-confirmation pre-computation (Part 9). The
        # "claimed direction" being tested must come from the NEWS
        # narrative, not from the price itself - comparing price against a
        # direction derived from that same price would be circular and
        # would never be able to detect a genuine news-vs-price divergence
        # (Part 33 Case A: positive AI capex news but SMH/QQQ falling).
        # A matched cluster is treated as a generically supportive catalyst
        # for the theme it's tagged to (a simplifying assumption for this
        # deterministic layer; a real LLM instead judges each article's
        # actual directionality from its text). With no matching news,
        # there is no narrative to test, so price_confirmation reports the
        # raw move context instead of a confirmed/diverged verdict.
        price_check = price_check_for_tickers(snapshot, etfs)
        avg_move = (
            sum(m["daily_pct"] for m in etf_moves) / len(etf_moves) if etf_moves else 0.0
        )
        if matching_clusters:
            price_confirmation = summarize_price_confirmation(price_check, "BULLISH")
        elif not etf_moves:
            price_confirmation = "数据不足"
        else:
            price_confirmation = "中性"

        themes_payload.append(
            {
                "key": theme["key"],
                "name": theme["name"],
                "related_etf_moves": etf_moves,
                "price_confirmation": price_confirmation,
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
