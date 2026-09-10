"""Company-level analysis connected to earnings drivers (Section 16;
V2 Part 12-13: Company Radar v2 - signal / what changed / driver
(taught inline) / expectation impact / deterministic price check / what
to watch next)."""
from __future__ import annotations

from typing import Dict, List, Optional

from src.analysis.llm_client import call_llm_json
from src.analysis.price_check import price_check_for_tickers
from src.models.schemas import CompanyAnalysis, CompanyAnalysisList, MarketSnapshot, NewsCluster
from src.providers.llm_base import LLMProvider
from src.utils.config import Settings

TASK = "company_analysis"

INSTRUCTIONS = """For each company in INPUT_DATA.companies, identify the SINGLE most relevant \
earnings driver implied by its matching news (if any is clearly implied), and TEACH it briefly in \
driver_explanation - assume the reader is a junior analyst who may not know the term: one short \
plain-language sentence defining the metric, then one sentence on why it matters here, e.g. \
"Bookings（订单额）代表客户新签订单，是观察未来收入的重要领先指标之一，但订单不一定会立即确认成 revenue。" \
Do NOT just say "bullish"/"bearish" - explain the mechanism.

relevant_driver must be one of: Revenue growth, ASP, Volume, Gross margin, Operating margin, \
Capex, Bookings, Backlog, ARR, Take rate, Customer concentration, Inventory, Pricing, Market share, \
Unit economics, Free cash flow, Buybacks, Guidance, Valuation - or null if none clearly applies.

signal must be one of POSITIVE, NEUTRAL, NEGATIVE, WATCH - WATCH means "something changed and is \
worth tracking" without a clear positive/negative lean yet.

INPUT_DATA.companies[].price_check is a DETERMINISTIC pre-computed list of the ticker's actual \
price move (e.g. ["NVDA +0.5%"]) - copy it verbatim into your output, never invent or alter it. \
Use it to inform expectation_impact: whether the disclosed news appears to already be reflected in \
the price, or represents a change to expectations (Part 25 framework), using hedged language.

Return JSON:
{
  "companies": [
    {
      "ticker": "...",
      "company_name": "...",
      "signal": "POSITIVE" | "NEUTRAL" | "NEGATIVE" | "WATCH",
      "what_changed": "one-line factual summary of the relevant news",
      "relevant_driver": "..." or null,
      "driver_explanation": "plain-language definition + why it matters here (see above)",
      "expectation_impact": "hedged read on expectations/consensus impact, or null",
      "price_check": ["copied verbatim from INPUT_DATA.companies[].price_check"],
      "what_to_watch_next": "concrete next data point/disclosure to watch",
      "theme_keys": ["..."],
      "confidence_pct": integer 0-100,
      "source_ids": ["cluster_id(s) used"]
    }, ...
  ]
}
Only include companies that actually appear in INPUT_DATA.companies with real matching news - do \
not add companies not present in the input."""


def analyze_companies(
    llm: LLMProvider,
    clusters: List[NewsCluster],
    settings: Settings,
    max_companies: int = 5,
    snapshot: Optional[MarketSnapshot] = None,
) -> List[CompanyAnalysis]:
    ticker_to_name: Dict[str, str] = {}
    for group in settings.watchlist.values():
        for entry in group:
            ticker_to_name[entry["ticker"]] = entry["name"]

    by_ticker: Dict[str, List[NewsCluster]] = {}
    for c in clusters:
        if c.unclassified:
            continue
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
            "price_check": price_check_for_tickers(snapshot, [ticker]) if snapshot is not None else [],
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
        companies = result.companies
        by_ticker_pc = {p["ticker"]: p["price_check"] for p in payload}
        for c in companies:
            if c.ticker in by_ticker_pc:
                c.price_check = by_ticker_pc[c.ticker]
        return companies
    return []
