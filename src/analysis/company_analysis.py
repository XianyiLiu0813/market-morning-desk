"""Company-level analysis connected to earnings drivers (Section 16)."""
from __future__ import annotations

from typing import Dict, List

from src.models.schemas import CompanyAnalysis, CompanyAnalysisList, NewsCluster
from src.providers.llm_base import LLMProvider
from src.analysis.llm_client import call_llm_json
from src.utils.config import Settings

TASK = "company_analysis"

INSTRUCTIONS = """For each company in INPUT_DATA.companies, identify the SINGLE most relevant \
earnings driver implied by its matching news (if any is clearly implied), and explain the \
mechanism connecting the news to that driver - do not just say "bullish"/"bearish", explain WHY \
(e.g. "if X increases HBM mix, it could improve blended ASP and potentially gross margin").

relevant_driver must be one of: Revenue growth, ASP, Volume, Gross margin, Operating margin, \
Capex, Bookings, Backlog, ARR, Take rate, Customer concentration, Inventory, Pricing, Market share, \
Unit economics, Free cash flow, Buybacks, Guidance, Valuation - or null if none clearly applies.

Return JSON:
{
  "companies": [
    {
      "ticker": "...",
      "company_name": "...",
      "headline": "one-line summary of the relevant news",
      "relevant_driver": "..." or null,
      "explanation": "the causal mechanism, hedged appropriately",
      "theme_keys": ["..."],
      "confidence_pct": integer 0-100,
      "source_ids": ["cluster_id(s) used"]
    }, ...
  ]
}
Only include companies that actually appear in INPUT_DATA.companies with real matching news - do \
not add companies not present in the input."""


def analyze_companies(
    llm: LLMProvider, clusters: List[NewsCluster], settings: Settings, max_companies: int = 5
) -> List[CompanyAnalysis]:
    ticker_to_name: Dict[str, str] = {}
    for group in settings.watchlist.values():
        for entry in group:
            ticker_to_name[entry["ticker"]] = entry["name"]

    by_ticker: Dict[str, List[NewsCluster]] = {}
    for c in clusters:
        for t in c.tickers:
            if t in ticker_to_name:
                by_ticker.setdefault(t, []).append(c)

    ranked_tickers = sorted(
        by_ticker.items(),
        key=lambda kv: max(c.importance.total for c in kv[1]),
        reverse=True,
    )[:max_companies]

    if not ranked_tickers:
        return []

    payload = [
        {
            "ticker": ticker,
            "company_name": ticker_to_name.get(ticker, ticker),
            "matching_stories": [
                {"cluster_id": c.cluster_id, "title": c.title, "fact_hint": c.fact_hint, "themes": c.themes}
                for c in cs
            ],
        }
        for ticker, cs in ranked_tickers
    ]
    input_data = {"companies": payload}
    result = call_llm_json(llm, TASK, INSTRUCTIONS, input_data, CompanyAnalysisList)
    if result is not None:
        return result.companies
    return []
