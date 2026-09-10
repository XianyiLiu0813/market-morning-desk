"""Trade idea generation (Section 18; V2 Part 14-17) - conservative, max 3,
0 allowed (Principle 5).

V2 change: a candidate must satisfy at least 3 of 5 evidence conditions to
be presented as a Trade Idea at all (Part 14) - anything with fewer stays
off the report entirely rather than being forced into a "LONG WATCH". The
gate runs in Python on the LLM's own output fields (not a second LLM
call), so it is cheap, deterministic, and auditable - the exact same rule
applies whether the analysis engine is the mock generator or a real LLM.
"""
from __future__ import annotations

from typing import Dict, List

from src.analysis.llm_client import call_llm_json
from src.models.schemas import CompanyAnalysis, ThemeView, TradeIdea, TradeIdeaList
from src.providers.llm_base import LLMProvider

TASK = "trade_ideas"

# Part 14: the five conditions a setup is graded against.
EVIDENCE_CONDITIONS = [
    "fundamental_catalyst",
    "price_confirmation",
    "expectations_changing",
    "asymmetric_risk_reward",
    "clear_invalidation",
]
MIN_CONDITIONS_REQUIRED = 3

INSTRUCTIONS = """Given INPUT_DATA.themes (theme views, each with structural_view AND \
tactical_view) and INPUT_DATA.companies (company analyses, each with a deterministic price_check), \
propose AT MOST 3 trade setups. It is entirely acceptable and often correct to propose ZERO if \
nothing meets a reasonably high bar - do not force an idea.

Every idea MUST answer: "what is the market potentially mispricing?" (edge_or_mispricing, Part 15) \
- if today's news merely confirms what was already consensus/priced-in, do not force a setup; write \
that explicitly in edge_or_mispricing and either omit the idea or mark direction "WAIT" with a low \
confidence_pct.

direction must be one of: "LONG WATCH", "SHORT WATCH", "WAIT", "AVOID", "NO TRADE". A strong \
structural theme with weak tactical/price confirmation should generally be "WAIT", not "LONG WATCH".

Do NOT invent specific price levels - describe entry/target/invalidation conditionally (e.g. "if X \
breaks below its recent range" rather than a specific number), since INPUT_DATA does not contain \
reliable intraday price levels.

Include junior_lesson: one sentence teaching WHY this is/isn't a valid setup (Part 16 example: \
"这里不是因为 ASML 是好公司就做多。真正需要判断的是：未来盈利预期有没有上修空间，以及当前股价是否已经反映这一预期。").

Return JSON:
{
  "ideas": [
    {
      "ticker": "...",
      "direction": "...",
      "structural_view": "short phrase, e.g. '结构性看多'",
      "tactical_view": "short phrase, e.g. '战术性中性/观望'",
      "thesis": "...",
      "edge_or_mispricing": "what the market may be under/over-pricing, or explicit 'no clear edge today'",
      "catalyst": "the fundamental catalyst behind this idea",
      "why_now": "...",
      "confirmation_required": "what market confirmation is needed",
      "entry_condition": "conditional, no invented price levels",
      "invalidation_condition": "conditional, no invented price levels - required if direction is a WATCH",
      "target_logic": "conditional reasoning, not a specific price",
      "risk_reward": "qualitative assessment - state explicitly if it looks asymmetric and why",
      "time_horizon": "e.g. 1-4 weeks",
      "key_risks": ["..."],
      "confidence_pct": integer 0-100 (keep modest, max ~65),
      "confidence_level": "HIGH" | "MEDIUM" | "LOW",
      "why_not_to_trade": "a real counterargument",
      "junior_lesson": "one sentence teaching the reasoning process",
      "source_ids": ["cluster_id or theme_key used"]
    }, ...
  ]
}
ideas may be an empty list."""


def evaluate_conditions(idea: TradeIdea) -> List[str]:
    """Part 14/32 CHECK 6: which of the 5 evidence conditions does this
    candidate satisfy? Runs on the already-produced TradeIdea object so the
    same check applies uniformly to mock and real-LLM output."""
    met: List[str] = []
    if idea.catalyst and len(idea.catalyst.strip()) > 5:
        met.append("fundamental_catalyst")
    confirmation_text = (idea.confirmation_required or "").lower()
    if any(kw in confirmation_text for kw in ("价格", "relative strength", "price", "强度")):
        met.append("price_confirmation")
    if idea.edge_or_mispricing and "无明显" not in idea.edge_or_mispricing and "no clear edge" not in idea.edge_or_mispricing.lower():
        met.append("expectations_changing")
    if idea.risk_reward and len(idea.risk_reward.strip()) > 8:
        met.append("asymmetric_risk_reward")
    if idea.invalidation_condition and len(idea.invalidation_condition.strip()) > 5:
        met.append("clear_invalidation")
    return met


def passes_threshold(idea: TradeIdea) -> bool:
    conditions = evaluate_conditions(idea)
    idea.conditions_met = conditions
    return len(conditions) >= MIN_CONDITIONS_REQUIRED


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

    # Part 14 gate: only ideas clearing >= MIN_CONDITIONS_REQUIRED of the 5
    # evidence conditions survive as a Trade Idea. This is intentionally
    # stricter than "the LLM proposed it" - a candidate that fails the gate
    # is dropped entirely rather than downgraded, since a half-supported
    # "LONG WATCH" is exactly the pattern Part 14 exists to prevent.
    surviving = [idea for idea in result.ideas if passes_threshold(idea)]
    # Directions that are inherently "no real setup" (WAIT/AVOID/NO TRADE)
    # don't need to clear the same bar - they're already conservative.
    non_directional = [
        idea for idea in result.ideas
        if idea not in surviving and idea.direction.value in ("WAIT", "AVOID", "NO TRADE")
    ]
    final = (surviving + non_directional)[:max_ideas]
    return final
