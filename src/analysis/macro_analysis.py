"""Macro story selection (Section 4/7).

Splits scored clusters into "macro" (rates, central banks, government data -
Section 7 topics, generally no single-company tickers) vs "market mover"
clusters (company/theme-tagged). Both get the same StoryAnalysis treatment
via analysis/story_analysis.py - this module just decides which bucket a
cluster belongs to, plus builds the day's macro calendar entries.
"""
from __future__ import annotations

from typing import List

from src.models.schemas import NewsCluster

MACRO_KEYWORDS = [
    "fed", "federal reserve", "treasury", "cpi", "pce", "ppi", "payroll", "jobless",
    "jolts", "gdp", "ism", "retail sales", "consumer sentiment", "yield curve",
    "pboc", "china macro", "property sector", "tariff", "geopolitic", "rate cut",
    "rate hike", "interest rate", "auction", "policy rate", "stimulus",
]


def is_macro_cluster(cluster: NewsCluster) -> bool:
    text = cluster.title.lower() + " " + (cluster.fact_hint or "").lower()
    has_macro_kw = any(kw in text for kw in MACRO_KEYWORDS)
    has_company_ticker = len(cluster.tickers) > 0
    # A cluster can mention tickers AND be macro-driven (e.g. PBOC cut
    # affecting HK tech) - prioritize macro classification when strong
    # macro keywords are present, even with tickers attached.
    return has_macro_kw


def split_macro_vs_market(clusters: List[NewsCluster]) -> tuple[List[NewsCluster], List[NewsCluster]]:
    macro, market = [], []
    for c in clusters:
        (macro if is_macro_cluster(c) else market).append(c)
    return macro, market
