"""Final editorial synthesis (Section 42: the daily mental model; also
produces the 60-second view fields: three things that matter, main risk,
one-sentence summary, dominant narrative)."""
from __future__ import annotations

from typing import Any, Dict, List

from src.models.schemas import (
    CompanyAnalysis,
    EditorialSynthesis,
    MarketRegimeView,
    StoryAnalysis,
    ThemeView,
    TradeIdea,
)
from src.providers.llm_base import LLMProvider
from src.analysis.llm_client import call_llm_json

TASK = "editorial_synthesis"

INSTRUCTIONS = """Synthesize INPUT_DATA (regime, top stories, theme views, trade ideas) into a \
final editorial layer for a morning research note.

Return JSON:
{
  "three_things_that_matter": ["...", "...", "..."]  (exactly 3, ranked by importance),
  "main_risk_today": "the single biggest risk to the prevailing view today",
  "one_sentence_summary": "one sentence capturing the market's overall state",
  "dominant_narrative": "2-4 sentences on what the market is actually trading right now (e.g. \
rates, AI capex, growth, inflation, liquidity, China policy, geopolitics) - avoid just listing \
disconnected facts, explain the throughline",
  "mental_model": {
    "what_changed": "...",
    "what_did_not_change": "...",
    "what_is_market_pricing": "...",
    "what_is_consensus": "...",
    "what_could_market_be_wrong_about": "...",
    "what_data_would_change_view": "...",
    "which_assets_express_view_best": "...",
    "is_risk_reward_attractive": "..."
  }
}
Keep every field grounded in INPUT_DATA - use hedged language for anything inferential."""


def synthesize_report(
    llm: LLMProvider,
    regime: MarketRegimeView,
    top_stories: List[StoryAnalysis],
    themes: List[ThemeView],
    trade_ideas: List[TradeIdea],
) -> EditorialSynthesis:
    input_data: Dict[str, Any] = {
        "regime": regime.model_dump(mode="json"),
        "top_stories": [
            {"title": s.title, "fact": s.fact, "why_it_matters": s.why_it_matters}
            for s in top_stories[:7]
        ],
        "themes": [
            {"name": t.theme_name, "view": t.view.value, "momentum": t.momentum.value}
            for t in themes
        ],
        "trade_ideas": [
            {"ticker": i.ticker, "direction": i.direction.value, "thesis": i.thesis}
            for i in trade_ideas
        ],
    }
    result = call_llm_json(llm, TASK, INSTRUCTIONS, input_data, EditorialSynthesis)
    if result is not None:
        return result

    from src.models.schemas import MentalModel

    return EditorialSynthesis(
        three_things_that_matter=[s.title for s in top_stories[:3]] or ["今日未识别到重大事件。"],
        main_risk_today="编辑综合分析本次不可用；请直接查看下方各条独立的新闻解读。",
        one_sentence_summary=regime.summary,
        dominant_narrative="编辑综合分析引擎本次运行不可用。",
        mental_model=MentalModel(
            what_changed="暂不可用。",
            what_did_not_change="暂不可用。",
            what_is_market_pricing="暂不可用。",
            what_is_consensus="暂不可用。",
            what_could_market_be_wrong_about="暂不可用。",
            what_data_would_change_view="暂不可用。",
            which_assets_express_view_best="暂不可用。",
            is_risk_reward_attractive="暂不可用。",
        ),
    )
