"""Trade idea generation (Section 18) - conservative, max 3, 0 allowed
(Principle 5)."""
from __future__ import annotations

from typing import List

from src.models.schemas import CompanyAnalysis, ThemeView, TradeIdea, TradeIdeaList
from src.providers.llm_base import LLMProvider
from src.analysis.llm_client import call_llm_json

TASK = "trade_ideas"

INSTRUCTIONS = """Given INPUT_DATA.themes (theme views) and INPUT_DATA.companies (company \
analyses), propose AT MOST 3 trade setups. It is entirely acceptable and often correct to \
propose ZERO if nothing meets a reasonably high bar - do not force an idea.

Each idea, if proposed, must have direction one of: "LONG WATCH", "SHORT WATCH", "AVOID", \
"NO TRADE", and MUST include a concrete invalidation_condition and a why_not_to_trade \
counterargument. Do NOT invent specific price levels - describe entry/target/invalidation \
conditionally (e.g. "if X breaks below its recent range" rather than a specific number), since \
INPUT_DATA does not contain exact intraday price levels.

Return JSON:
{
  "ideas": [
    {
      "ticker": "...",
      "direction": "...",
      "thesis": "...",
      "catalyst": "...",
      "why_now": "...",
      "confirmation_required": "what market confirmation is needed",
      "entry_condition": "conditional, no invented price levels",
      "invalidation_condition": "conditional, no invented price levels",
      "target_logic": "conditional reasoning, not a specific price",
      "risk_reward": "qualitative assessment",
      "time_horizon": "e.g. 1-4 weeks",
      "key_risks": ["..."],
      "confidence_pct": integer 0-100 (keep modest, max ~65, since this is a watch idea not a call),
      "why_not_to_trade": "a real counterargument",
      "source_ids": ["cluster_id or theme_key used"]
    }, ...
  ]
}
ideas may be an empty list."""


def generate_trade_ideas(
    llm: LLMProvider, themes: List[ThemeView], companies: List[CompanyAnalysis], max_ideas: int = 3
) -> List[TradeIdea]:
    if not themes and not companies:
        return []
    input_data = {
        "themes": [t.model_dump(mode="json") for t in themes],
        "companies": [c.model_dump(mode="json") for c in companies],
    }
    result = call_llm_json(llm, TASK, INSTRUCTIONS, input_data, TradeIdeaList)
    if result is None:
        return []
    return result.ideas[:max_ideas]
