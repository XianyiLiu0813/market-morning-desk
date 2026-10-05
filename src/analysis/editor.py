"""Final editorial synthesis (Section 42: the daily mental model; also
produces the 60-second view fields: three things that matter, main risk,
one-sentence summary, dominant narrative)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.models.schemas import (
    CompanyAnalysis,
    EditorialSynthesis,
    MarketRegimeView,
    MarketSnapshot,
    StoryAnalysis,
    ThemeView,
    TradeIdea,
)
from src.providers.llm_base import LLMProvider
from src.analysis.llm_client import call_llm_json

TASK = "editorial_synthesis"

# Symbols pulled into INPUT_DATA.cross_asset_snapshot for dominant_narrative
# to cite concretely (Part: "cross-asset narrative enhancement" - borrowed
# from a sample morning note that threads ONE storyline through rates, FX,
# commodities and equities instead of listing them separately).
CROSS_ASSET_SYMBOLS = ["US2Y", "US10Y", "DXY", "GLD", "CL=F", "^VIX"]

INSTRUCTIONS = """Synthesize INPUT_DATA (regime, top stories, theme views, trade ideas, \
cross_asset_snapshot) into a final editorial layer for a morning research note. Each theme now \
carries an INDEPENDENT structural_view (multi-quarter thesis) and tactical_view (days-to-weeks \
trade-worthiness) - when you reference a theme, be precise about which one you mean (a \
structurally bullish theme can still be tactically neutral this week).

For dominant_narrative specifically: build ONE coherent cross-asset storyline and cite 2-3 \
SPECIFIC numbers from INPUT_DATA.cross_asset_snapshot to support it (e.g. "US10Y moved X bp while \
DXY did Y, consistent with..." ) - don't just list each asset's move in isolation; explain how they \
confirm or contradict each other under the dominant theme. If rates/VIX/gold/oil don't cohere into \
one clean story today, say so explicitly (e.g. "cross-asset signals are mixed: X points one way, Y \
points another") rather than forcing a false throughline (Principle 4: avoid false causality).

For key_dislocations: scan INPUT_DATA.themes for cases where a theme's structural_view and \
tactical_view disagree (e.g. structurally bullish but tactically neutral/bearish), or where its \
price_confirmation ("确认"/"中性"/"背离"/"数据不足") doesn't match its structural stance (e.g. \
strongly bullish structurally but price_confirmation is "中性" or "数据不足"). Each is a genuine \
fundamental-vs-price divergence worth flagging as something to keep watching, NOT a trade call. \
Return 0-4 short (1 sentence) bullets; return an empty list if nothing meaningfully diverges today \
- do not manufacture a dislocation where the data doesn't support one.

Return JSON:
{
  "three_things_that_matter": ["...", "...", "..."]  (exactly 3, ranked by importance),
  "main_risk_today": "the single biggest risk to the prevailing view today",
  "one_sentence_summary": "one sentence capturing the market's overall state",
  "dominant_narrative": "2-4 sentences on what the market is actually trading right now (e.g. \
rates, AI capex, growth, inflation, liquidity, China policy, geopolitics), citing 2-3 specific \
cross_asset_snapshot numbers - avoid just listing disconnected facts, explain the throughline",
  "key_dislocations": ["...", ...]  (0-4 bullets, see above - empty list if none today),
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


def _build_cross_asset_snapshot(snapshot: Optional[MarketSnapshot]) -> List[Dict[str, Any]]:
    if snapshot is None:
        return []
    out = []
    for sym in CROSS_ASSET_SYMBOLS:
        asset = snapshot.get(sym)
        if asset is None:
            continue
        if asset.is_rate:
            out.append({
                "symbol": sym, "display_name": asset.display_name,
                "level": asset.last_price, "bp_change": asset.bp_change,
            })
        else:
            out.append({
                "symbol": sym, "display_name": asset.display_name,
                "daily_pct": asset.daily_pct,
            })
    return out


def synthesize_report(
    llm: LLMProvider,
    regime: MarketRegimeView,
    top_stories: List[StoryAnalysis],
    themes: List[ThemeView],
    trade_ideas: List[TradeIdea],
    snapshot: Optional[MarketSnapshot] = None,
) -> EditorialSynthesis:
    input_data: Dict[str, Any] = {
        "regime": regime.model_dump(mode="json"),
        "cross_asset_snapshot": _build_cross_asset_snapshot(snapshot),
        "top_stories": [
            {"title": s.title, "fact": s.fact, "why_it_matters": s.why_it_matters}
            for s in top_stories[:7]
        ],
        "themes": [
            {
                "name": t.theme_name,
                "structural_view": t.structural_view.value,
                "tactical_view": t.tactical_view.value,
                "momentum": t.momentum.value,
                "price_confirmation": t.price_confirmation,
                "risk": t.risk,
            }
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
