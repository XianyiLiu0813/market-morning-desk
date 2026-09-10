"""Structured story write-ups (Section 15) + macro story split (Section 4).

Two categories are produced from the same underlying analysis call:
- macro_stories: clusters with no company tickers (rates, central banks, etc.)
- top_stories: clusters with company/theme relevance (the "what actually
  mattered overnight" section)
The split happens in the caller (main pipeline) based on cluster.tickers,
not here - this module just turns a batch of clusters into StoryAnalysis
objects in one LLM call.

V2 Part 9: price_check is computed in Python from the validated snapshot
BEFORE the LLM call and handed over as ground truth - the LLM's job is to
interpret it ("market_impact"/"expectation_impact"), never to invent it.
"""
from __future__ import annotations

from typing import Dict, List

from src.analysis.llm_client import call_llm_json
from src.analysis.price_check import price_check_for_tickers
from src.models.schemas import MarketSnapshot, NewsCluster, StoryAnalysis, StoryAnalysisList
from src.providers.llm_base import LLMProvider

TASK = "story_analysis"

INSTRUCTIONS = """For each cluster in INPUT_DATA.clusters, produce a full structured story \
analysis. Base FACT strictly on the cluster's fact_hint/title/source data - do not add facts not \
present there. WHY_IT_MATTERS, effects, and beneficiaries should draw on the theme's drivers/ \
upstream/downstream context provided per cluster, expressed as reasoned inference (interpretation), \
clearly hedged where uncertain. When referring to a theme in prose, use the human-readable name \
from theme_names (e.g. "AI Compute"), never the raw snake_case key from `themes` (e.g. "ai_compute") \
- the keys are only for machine cross-referencing.

INPUT_DATA.clusters[].price_check is a DETERMINISTIC, pre-computed list of actual ticker moves \
(e.g. ["NVDA +0.5%", "SMH -0.6%"]) - copy it into your output's price_check field VERBATIM, never \
invent, alter, or add to it. Use it to write market_impact: explicitly note whether the market \
actually traded this news in the direction the headline implies, is mixed, or shows no reaction \
(Part 9: "news mattering" and "stock moving" are different claims - do not conflate them). Also \
set expectation_impact: a short read on whether this changes consensus estimates/expectations, or \
merely confirms what was already expected (Part 25 expectation framework: actual vs consensus vs \
priced-in vs price reaction) - use hedged language since INPUT_DATA rarely contains actual \
consensus figures.

Return JSON:
{
  "stories": [
    {
      "cluster_id": "...",
      "title": "...",
      "importance": one of HIGH, MEDIUM, LOW,
      "source_names": ["..."],
      "fact": "objectively confirmed statement, grounded in fact_hint",
      "why_it_matters": "...",
      "market_impact": "did price action confirm, contradict, or show no reaction to this news",
      "price_check": ["copied verbatim from INPUT_DATA.clusters[].price_check"],
      "expectation_impact": "hedged read on consensus/expectations impact, or null",
      "first_order_effect": "who/what is most directly affected",
      "second_order_effect": "indirect/downstream effect, or null if too speculative",
      "who_benefits": ["ticker or entity", ...],
      "who_may_be_hurt": ["ticker or entity", ...],
      "is_priced_in": "your assessment, hedged, or null",
      "what_to_watch_next": "...",
      "what_would_invalidate": "what evidence would prove this reading wrong",
      "confidence_pct": integer 0-100,
      "source_ids": ["the cluster_id"],
      "urls": ["from cluster's urls field"]
    }, ...
  ]
}"""


def analyze_stories(
    llm: LLMProvider,
    clusters: List[NewsCluster],
    theme_context: dict,
    snapshot: MarketSnapshot = None,
) -> List[StoryAnalysis]:
    if not clusters:
        return []
    payload = []
    for c in clusters:
        theme_ctx = [theme_context.get(t, {}) for t in c.themes if t in theme_context]
        theme_names = [theme_context[t]["name"] for t in c.themes if t in theme_context]
        price_check = price_check_for_tickers(snapshot, c.tickers) if snapshot is not None else []
        payload.append(
            {
                "cluster_id": c.cluster_id,
                "title": c.title,
                "fact_hint": c.fact_hint,
                "tickers": c.tickers,
                "themes": c.themes,
                "theme_names": theme_names,
                "theme_context": theme_ctx,
                "price_check": price_check,
                "source_names": c.source_names,
                "best_tier": c.best_tier,
                "urls": c.urls,
                "importance_score": c.importance.total,
            }
        )
    input_data = {"clusters": payload}
    result = call_llm_json(llm, TASK, INSTRUCTIONS, input_data, StoryAnalysisList)
    if result is not None:
        stories = result.stories
        # Belt-and-suspenders: force price_check to the deterministic value
        # regardless of what the LLM echoed back, so a model that "helpfully"
        # tweaks a number can never introduce a hallucinated price into the
        # report (Section 26).
        by_cluster = {p["cluster_id"]: p["price_check"] for p in payload}
        for s in stories:
            if s.cluster_id in by_cluster:
                s.price_check = by_cluster[s.cluster_id]
        return stories
    return []
