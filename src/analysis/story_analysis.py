"""Structured story write-ups (Section 15) + macro story split (Section 4).

Two categories are produced from the same underlying analysis call:
- macro_stories: clusters with no company tickers (rates, central banks, etc.)
- top_stories: clusters with company/theme relevance (the "what actually
  mattered overnight" section)
The split happens in the caller (main pipeline) based on cluster.tickers,
not here - this module just turns a batch of clusters into StoryAnalysis
objects in one LLM call.
"""
from __future__ import annotations

from typing import List

from src.models.schemas import NewsCluster, StoryAnalysis, StoryAnalysisList
from src.providers.llm_base import LLMProvider
from src.analysis.llm_client import call_llm_json

TASK = "story_analysis"

INSTRUCTIONS = """For each cluster in INPUT_DATA.clusters, produce a full structured story \
analysis. Base FACT strictly on the cluster's fact_hint/title/source data - do not add facts not \
present there. WHY_IT_MATTERS, effects, and beneficiaries should draw on the theme's drivers/ \
upstream/downstream context provided per cluster, expressed as reasoned inference (interpretation), \
clearly hedged where uncertain. When referring to a theme in prose, use the human-readable name \
from theme_names (e.g. "AI Compute"), never the raw snake_case key from `themes` (e.g. "ai_compute") \
- the keys are only for machine cross-referencing.

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
      "market_impact": "short description or null",
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


def analyze_stories(llm: LLMProvider, clusters: List[NewsCluster], theme_context: dict) -> List[StoryAnalysis]:
    if not clusters:
        return []
    payload = []
    for c in clusters:
        theme_ctx = [theme_context.get(t, {}) for t in c.themes if t in theme_context]
        theme_names = [theme_context[t]["name"] for t in c.themes if t in theme_context]
        payload.append(
            {
                "cluster_id": c.cluster_id,
                "title": c.title,
                "fact_hint": c.fact_hint,
                "tickers": c.tickers,
                "themes": c.themes,
                "theme_names": theme_names,
                "theme_context": theme_ctx,
                "source_names": c.source_names,
                "best_tier": c.best_tier,
                "urls": c.urls,
                "importance_score": c.importance.total,
            }
        )
    input_data = {"clusters": payload}
    result = call_llm_json(llm, TASK, INSTRUCTIONS, input_data, StoryAnalysisList)
    if result is not None:
        return result.stories
    return []
