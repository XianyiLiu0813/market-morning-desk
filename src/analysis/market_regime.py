"""Market regime inference (Section 13)."""
from __future__ import annotations

from typing import Dict, List

from src.models.schemas import MarketRegimeView, MarketSnapshot, NewsCluster
from src.providers.llm_base import LLMProvider
from src.analysis.llm_client import call_llm_json

TASK = "market_regime"

INSTRUCTIONS = """Given the market data snapshot and today's top news clusters in INPUT_DATA, \
infer today's market regime.

Return JSON matching this schema:
{
  "labels": [one or more of: RISK_ON, RISK_OFF, MIXED, GROWTH_LED, VALUE_LED, AI_LED, \
RATE_DRIVEN, MACRO_DRIVEN, DEFENSIVE, LIQUIDITY_DRIVEN, VOLATILITY_EVENT],
  "confidence_pct": integer 0-100,
  "summary": "one or two sentence summary of the regime",
  "supporting_evidence": ["short evidence bullet", ...],
  "contradicting_evidence": ["short evidence bullet describing what does NOT fit this regime", ...],
  "source_ids": ["cluster_id or source_id strings you drew on"]
}

Important: check whether the move is BROAD (most assets moving together) or CONCENTRATED \
(e.g. only semiconductors/AI names moving while small caps lag) - a concentrated move should be \
labeled AI_LED or GROWTH_LED rather than a blanket RISK_ON, and you should note the concentration \
explicitly as either supporting or contradicting evidence for broad risk-on."""


def _asset_brief(snapshot: MarketSnapshot) -> List[Dict]:
    keep_symbols = {
        "^GSPC", "^IXIC", "^RUT", "^HSI", "^HSTECH", "^VIX", "US10Y", "US2Y", "DXY",
        "QQQ", "SMH", "SOXX", "IWM", "XLK", "GLD", "CL=F", "KWEB",
    }
    return [
        {
            "symbol": a.symbol,
            "name": a.display_name,
            "daily_pct": a.daily_pct,
        }
        for a in snapshot.assets
        if a.symbol in keep_symbols
    ]


def infer_market_regime(
    llm: LLMProvider, snapshot: MarketSnapshot, top_clusters: List[NewsCluster]
) -> MarketRegimeView:
    input_data = {
        "assets": _asset_brief(snapshot),
        "top_stories": [
            {"cluster_id": c.cluster_id, "title": c.title, "themes": c.themes}
            for c in top_clusters[:7]
        ],
    }
    result = call_llm_json(llm, TASK, INSTRUCTIONS, input_data, MarketRegimeView)
    if result is not None:
        return result

    # Safe degraded fallback: never block the pipeline on a bad LLM response.
    return MarketRegimeView(
        labels=["MIXED"],
        confidence_pct=0,
        summary="Market regime could not be determined (analysis engine unavailable or invalid response).",
        supporting_evidence=[],
        contradicting_evidence=[],
        source_ids=[],
    )
