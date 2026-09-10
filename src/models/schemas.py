"""Pydantic schemas used across the pipeline.

These are the internal data contracts. Every LLM call in src/analysis/*
must validate its JSON output against one of these models before it's
allowed to flow into report rendering (Section 25/26 - hallucination
guardrails). If validation fails, the caller must fall back to a safe
degraded value, never invent one.

V2 additions (see market-morning-desk V2 upgrade notes):
- MarketAsset carries `is_rate` + a basis-point change helper so Treasury
  yields display as level + bp, not a raw percent-of-percent.
- ThemeView splits a single BULLISH/BEARISH label into independent
  structural (multi-quarter) and tactical (days-to-weeks) views.
- StoryAnalysis/CompanyAnalysis carry a deterministic, Python-computed
  `price_check` - never LLM-invented - so "did the market actually trade
  this" is always grounded in the validated snapshot.
- TradeIdea carries `edge_or_mispricing` and `conditions_met` so a setup
  must show its work, not just assert a direction.
- LearnOneThing is now a structured 5-part lesson instead of a free-form
  paragraph.
"""
from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------

class SourceTier(int, Enum):
    PRIMARY = 1
    HIGH_QUALITY_MEDIA = 2
    SECONDARY_MEDIA = 3
    SOCIAL_CHATTER = 4


class Sentiment(str, Enum):
    BULLISH = "BULLISH"
    SLIGHTLY_BULLISH = "SLIGHTLY_BULLISH"
    NEUTRAL = "NEUTRAL"
    SLIGHTLY_BEARISH = "SLIGHTLY_BEARISH"
    BEARISH = "BEARISH"


class Momentum(str, Enum):
    IMPROVING = "IMPROVING"
    UNCHANGED = "UNCHANGED"
    DETERIORATING = "DETERIORATING"


class TradeDirection(str, Enum):
    LONG_WATCH = "LONG WATCH"
    SHORT_WATCH = "SHORT WATCH"
    WAIT = "WAIT"
    AVOID = "AVOID"
    NO_TRADE = "NO TRADE"


class RegimeLabel(str, Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    MIXED = "MIXED"
    GROWTH_LED = "GROWTH_LED"
    VALUE_LED = "VALUE_LED"
    AI_LED = "AI_LED"
    RATE_DRIVEN = "RATE_DRIVEN"
    MACRO_DRIVEN = "MACRO_DRIVEN"
    DEFENSIVE = "DEFENSIVE"
    LIQUIDITY_DRIVEN = "LIQUIDITY_DRIVEN"
    VOLATILITY_EVENT = "VOLATILITY_EVENT"


class ImportanceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CompanySignal(str, Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    WATCH = "WATCH"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# --------------------------------------------------------------------------
# Market data
# --------------------------------------------------------------------------

class MarketAsset(BaseModel):
    """A single asset's price snapshot for one trading session."""

    symbol: str
    display_name: str
    group: str
    previous_close: Optional[float] = None
    last_price: Optional[float] = None
    daily_pct: Optional[float] = None
    overnight_pct: Optional[float] = None
    volume: Optional[float] = None
    relative_volume: Optional[float] = None
    return_5d_pct: Optional[float] = None
    return_1m_pct: Optional[float] = None
    pct_from_52w_high: Optional[float] = None
    as_of: Optional[datetime] = None
    data_source: str = "unknown"
    is_stale: bool = False
    # V2: rate-type assets (Treasury yields, 2s10s) must never be displayed
    # as a plain percent change (Part 4) - `last_price`/`previous_close`
    # for these are already yield levels in percentage-point units, so the
    # basis-point delta is (last_price - previous_close) * 100.
    is_rate: bool = False

    @field_validator(
        "daily_pct", "return_5d_pct", "return_1m_pct", "pct_from_52w_high",
        "last_price", "previous_close", "overnight_pct", "volume", "relative_volume",
    )
    @classmethod
    def reject_nan_inf(cls, v: Optional[float]) -> Optional[float]:
        """A NaN/inf value must never reach the report as a number - it has
        to become an explicit "data unavailable", not a `nan%` string
        (Part 2 P0 data-quality gate). Coercing to None here means every
        consumer (renderer, dashboard logic, price-check text) automatically
        treats it as missing, rather than each call site needing its own
        isnan() check."""
        if v is None:
            return None
        import math

        if math.isnan(v) or math.isinf(v):
            return None
        return v

    @property
    def bp_change(self) -> Optional[float]:
        """Basis-point change for rate-type assets. None for non-rate
        assets or when levels are unavailable."""
        if not self.is_rate or self.previous_close is None or self.last_price is None:
            return None
        return round((self.last_price - self.previous_close) * 100, 1)


class MarketSnapshot(BaseModel):
    """The single validated market data object every analysis module reads
    from (Part 3: ValidatedMarketSnapshot) - no module may independently
    invent or re-fetch a price; if it's not in here, it's "data unavailable"."""

    run_date: date
    generated_at: datetime
    assets: List[MarketAsset] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    core_assets_missing: List[str] = Field(default_factory=list)

    def get(self, symbol: str) -> Optional[MarketAsset]:
        for a in self.assets:
            if a.symbol == symbol:
                return a
        return None


# --------------------------------------------------------------------------
# News
# --------------------------------------------------------------------------

class SourceRecord(BaseModel):
    """A single fetched piece of source content (Section 6/28: source_records)."""

    source_id: str
    source_name: str
    tier: SourceTier
    kind: str = "unknown"  # api | rss | edgar | direct
    url: Optional[str] = None
    fetched_at: datetime


class NewsArticle(BaseModel):
    article_id: str
    title: str
    summary: Optional[str] = None
    body_excerpt: Optional[str] = None
    url: Optional[str] = None
    source_id: str
    source_name: str
    tier: SourceTier
    published_at: Optional[datetime] = None
    tickers: List[str] = Field(default_factory=list)
    themes: List[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Article title must not be empty")
        return v.strip()


class ImportanceScore(BaseModel):
    market_impact: float = Field(ge=0, le=5, default=0)
    source_quality: float = Field(ge=0, le=5, default=0)
    novelty: float = Field(ge=0, le=5, default=0)
    theme_relevance: float = Field(ge=0, le=5, default=0)
    company_relevance: float = Field(ge=0, le=5, default=0)
    price_confirmation: float = Field(ge=0, le=5, default=0)
    urgency: float = Field(ge=0, le=5, default=0)
    total: float = 0.0


class NewsCluster(BaseModel):
    """A group of articles reporting the same underlying event (Section 9)."""

    cluster_id: str
    representative_article_id: str
    member_article_ids: List[str] = Field(default_factory=list)
    title: str
    tickers: List[str] = Field(default_factory=list)
    themes: List[str] = Field(default_factory=list)
    importance: ImportanceScore = Field(default_factory=ImportanceScore)
    source_ids: List[str] = Field(default_factory=list)
    source_names: List[str] = Field(default_factory=list)
    source_tiers: Dict[str, int] = Field(default_factory=dict)
    urls: List[str] = Field(default_factory=list)
    best_tier: int = 2
    fact_hint: Optional[str] = None
    hours_since_publish: Optional[float] = None
    # V2 (Part 11 classification QA): set when theme/company auto-tagging
    # had low confidence - such clusters are excluded from theme analysis
    # rather than silently mis-filed (e.g. a PE deal landing under "Gold").
    unclassified: bool = False


# --------------------------------------------------------------------------
# Macro
# --------------------------------------------------------------------------

class MacroEvent(BaseModel):
    event: str
    scheduled_at_sgt: Optional[datetime] = None
    local_time_label: Optional[str] = None
    expected: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    importance: ImportanceLevel = ImportanceLevel.MEDIUM
    notes: Optional[str] = None
    # V2 (Part 19): watch list + conditional scenario framing, e.g.
    # "claims clearly above expected -> growth concern up -> yields may fall".
    assets_to_watch: List[str] = Field(default_factory=list)
    scenario: Optional[str] = None


# --------------------------------------------------------------------------
# Analysis outputs (all must carry facts/interpretation/confidence/source_ids
# per Section 26 hallucination guardrails)
# --------------------------------------------------------------------------

class MarketRegimeView(BaseModel):
    labels: List[RegimeLabel]
    confidence_pct: int = Field(ge=0, le=100)
    summary: str
    supporting_evidence: List[str] = Field(default_factory=list)
    contradicting_evidence: List[str] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list)


class TraderDashboard(BaseModel):
    """Part 5: deterministic, rule-based market-state read (not an LLM
    call) - six one-word-ish states a junior trader should register in the
    first 10 seconds of reading. Computed directly from the validated
    snapshot in src/analysis/market_state.py, never invented."""

    risk_appetite: str  # 改善 / 稳定 / 恶化
    rates: str  # 下行 / 持平 / 上行
    usd: str  # 走弱 / 持平 / 走强
    volatility: str  # 下降 / 持平 / 上升
    breadth: str  # 偏宽 / 分化 / 偏窄
    liquidity: str  # 支持性 / 中性 / 收紧（heuristic proxy - see notes）
    breadth_is_proxy: bool = True
    liquidity_is_proxy: bool = True


class ThemeView(BaseModel):
    """V2 (Part 7): a theme's structural (multi-quarter) view and tactical
    (days-to-weeks) view are tracked independently - a great long-term
    theme can still be TACTICAL = NEUTRAL/WAIT this week."""

    theme_key: str
    theme_name: str
    structural_view: Sentiment
    tactical_view: Sentiment
    momentum: Momentum
    structural_reason: str
    tactical_reason: str
    price_confirmation: str = "数据不足"  # Confirmed / Mixed / Weak / 数据不足
    evidence: List[str] = Field(default_factory=list)
    risk: Optional[str] = None
    change_vs_yesterday: Optional[str] = None
    confidence_pct: int = Field(ge=0, le=100, default=50)
    source_ids: List[str] = Field(default_factory=list)

    @property
    def is_meaningful_change(self) -> bool:
        """Exception-based reporting (Part 8): a theme only earns an
        expanded card if it genuinely changed vs yesterday (set by
        analysis/change_detection.py) OR has a fresh matching news story
        (source_ids non-empty) - NOT just because it has some price
        evidence, which nearly every theme has on any given day and would
        defeat the point of "don't waste the reader's attention"."""
        if self.change_vs_yesterday:
            return True
        return len(self.source_ids) > 0


class StoryAnalysis(BaseModel):
    """Full structured story write-up (Section 15), extended for V2 with a
    deterministic price_check and an explicit expectation framework
    (Part 25: actual vs consensus vs priced-in vs price reaction)."""

    cluster_id: str
    title: str
    importance: ImportanceLevel
    source_names: List[str] = Field(default_factory=list)
    fact: str
    why_it_matters: str
    market_impact: Optional[str] = None
    # V2: filled in Python from the validated snapshot, never by the LLM -
    # e.g. ["GOOGL -0.3%", "NVDA +0.5%", "SMH -0.6%"]. Empty list means no
    # relevant ticker had price data, not "not computed".
    price_check: List[str] = Field(default_factory=list)
    expectation_impact: Optional[str] = None
    first_order_effect: Optional[str] = None
    second_order_effect: Optional[str] = None
    who_benefits: List[str] = Field(default_factory=list)
    who_may_be_hurt: List[str] = Field(default_factory=list)
    is_priced_in: Optional[str] = None
    what_to_watch_next: Optional[str] = None
    what_would_invalidate: Optional[str] = None
    confidence_pct: int = Field(ge=0, le=100, default=50)
    source_ids: List[str] = Field(default_factory=list)
    urls: List[str] = Field(default_factory=list)


class EarningsDriver(str, Enum):
    REVENUE_GROWTH = "Revenue growth"
    ASP = "ASP"
    VOLUME = "Volume"
    GROSS_MARGIN = "Gross margin"
    OPERATING_MARGIN = "Operating margin"
    CAPEX = "Capex"
    BOOKINGS = "Bookings"
    BACKLOG = "Backlog"
    ARR = "ARR"
    TAKE_RATE = "Take rate"
    CUSTOMER_CONCENTRATION = "Customer concentration"
    INVENTORY = "Inventory"
    PRICING = "Pricing"
    MARKET_SHARE = "Market share"
    UNIT_ECONOMICS = "Unit economics"
    FREE_CASH_FLOW = "Free cash flow"
    BUYBACKS = "Buybacks"
    GUIDANCE = "Guidance"
    VALUATION = "Valuation"


class CompanyAnalysis(BaseModel):
    """V2 (Part 12): Company Radar now tracks signal/what-changed/
    expectation-impact/price-confirmation/next-watch instead of one
    headline + one paragraph."""

    ticker: str
    company_name: str
    signal: CompanySignal = CompanySignal.NEUTRAL
    what_changed: str
    relevant_driver: Optional[EarningsDriver] = None
    driver_explanation: str
    expectation_impact: Optional[str] = None
    # V2: filled in Python from the validated snapshot, same discipline as
    # StoryAnalysis.price_check.
    price_check: List[str] = Field(default_factory=list)
    what_to_watch_next: Optional[str] = None
    theme_keys: List[str] = Field(default_factory=list)
    confidence_pct: int = Field(ge=0, le=100, default=50)
    source_ids: List[str] = Field(default_factory=list)


class TradeIdea(BaseModel):
    """V2 (Part 14-17): a setup must show which evidence conditions it
    satisfies and what the market may be mispricing - not just assert a
    direction because a theme is bullish."""

    ticker: Optional[str] = None
    direction: TradeDirection
    structural_view: Optional[str] = None
    tactical_view: Optional[str] = None
    thesis: Optional[str] = None
    edge_or_mispricing: Optional[str] = None
    catalyst: Optional[str] = None
    why_now: Optional[str] = None
    confirmation_required: Optional[str] = None
    entry_condition: Optional[str] = None
    invalidation_condition: Optional[str] = None
    target_logic: Optional[str] = None
    risk_reward: Optional[str] = None
    time_horizon: Optional[str] = None
    key_risks: List[str] = Field(default_factory=list)
    confidence_pct: int = Field(ge=0, le=100, default=30)
    confidence_level: ConfidenceLevel = ConfidenceLevel.LOW
    why_not_to_trade: Optional[str] = None
    junior_lesson: Optional[str] = None
    # Part 32 CHECK 6/7/8: which of the 5 evidence conditions this setup
    # satisfied (see src/analysis/trade_analysis.py::EVIDENCE_CONDITIONS).
    conditions_met: List[str] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list)


class TradeIdeaList(BaseModel):
    """Wrapper enforcing Principle 5 / Section 18: max 3 trade setups, 0 allowed."""

    ideas: List[TradeIdea] = Field(default_factory=list)

    @field_validator("ideas")
    @classmethod
    def max_three(cls, v: List[TradeIdea]) -> List[TradeIdea]:
        if len(v) > 3:
            raise ValueError("A maximum of 3 trade ideas is allowed per Principle 5")
        return v


class TerminologyTerm(BaseModel):
    term: str
    plain_definition: str
    why_traders_care: str
    todays_example: Optional[str] = None


class LearnOneThing(BaseModel):
    """V2 (Part 20): a structured 5-part lesson instead of one free-form
    paragraph - question / concept / today's example / common beginner
    mistake / trader takeaway."""

    title: str
    question: str
    core_concept: str
    todays_example: str
    common_mistake: Optional[str] = None
    trader_takeaway: str
    tied_to_event: Optional[str] = None

    @model_validator(mode="after")
    def length_guard(self) -> "LearnOneThing":
        # See MarketAsset/V1 note on why this counts characters, not
        # whitespace-split "words" - CJK text has no spaces between words.
        total = len(self.question) + len(self.core_concept) + len(self.todays_example) + len(self.trader_takeaway)
        if total < 150:
            raise ValueError("Learn-one-thing content is too short to be useful (<150 characters combined)")
        return self


class MentalModel(BaseModel):
    """Section 42 - forced internal Q&A that guides final synthesis."""

    what_changed: str
    what_did_not_change: str
    what_is_market_pricing: str
    what_is_consensus: str
    what_could_market_be_wrong_about: str
    what_data_would_change_view: str
    which_assets_express_view_best: str
    is_risk_reward_attractive: str


class YesterdayReviewItem(BaseModel):
    ticker: str
    direction: TradeDirection
    original_thesis: str
    reference_price: Optional[float] = None
    subsequent_move_pct: Optional[float] = None
    max_favorable_excursion_pct: Optional[float] = None
    max_adverse_excursion_pct: Optional[float] = None
    thesis_intact: Optional[bool] = None
    lesson: Optional[str] = None


class DataQualityStatus(BaseModel):
    ok: bool = True
    warnings: List[str] = Field(default_factory=list)
    degraded_mode: bool = False
    reasons: List[str] = Field(default_factory=list)
    core_assets_missing: List[str] = Field(default_factory=list)


class MorningReport(BaseModel):
    """Top-level object handed to the HTML renderer."""

    run_date: date
    generated_at: datetime
    timezone: str

    dashboard: Optional[TraderDashboard] = None
    regime: MarketRegimeView
    what_changed_overnight: List[str] = Field(default_factory=list)
    three_things_that_matter: List[str] = Field(default_factory=list)
    main_risk_today: Optional[str] = None
    one_sentence_summary: Optional[str] = None

    market_snapshot: MarketSnapshot
    dominant_narrative: Optional[str] = None

    macro_events_today: List[MacroEvent] = Field(default_factory=list)
    macro_stories: List[StoryAnalysis] = Field(default_factory=list)

    theme_views: List[ThemeView] = Field(default_factory=list)
    top_stories: List[StoryAnalysis] = Field(default_factory=list)
    other_developments: List[str] = Field(default_factory=list)
    company_radar: List[CompanyAnalysis] = Field(default_factory=list)
    trade_ideas: List[TradeIdea] = Field(default_factory=list)

    learn_one_thing: Optional[LearnOneThing] = None
    terminology: List[TerminologyTerm] = Field(default_factory=list)

    mental_model: Optional[MentalModel] = None
    yesterday_review: List[YesterdayReviewItem] = Field(default_factory=list)

    data_quality: DataQualityStatus = Field(default_factory=DataQualityStatus)
    source_index: List[SourceRecord] = Field(default_factory=list)

    disclaimer: str = (
        "本报告是一个 AI 辅助的市场研究与学习工具，不构成投资建议（not financial advice）。"
        "信息可能不完整或存在误差，交易前请务必通过一手信息源（primary sources）核实关键信息。"
    )

    @field_validator("trade_ideas")
    @classmethod
    def max_three_ideas(cls, v: List[TradeIdea]) -> List[TradeIdea]:
        if len(v) > 3:
            raise ValueError("Maximum of 3 trade ideas allowed in a report")
        return v


# --------------------------------------------------------------------------
# LLM call wrapper schemas (a single LLM call often returns a list of
# objects; these wrap that list so call_llm_json has one Pydantic model per
# task to validate against).
# --------------------------------------------------------------------------

class StoryAnalysisList(BaseModel):
    stories: List[StoryAnalysis] = Field(default_factory=list)


class ThemeViewList(BaseModel):
    themes: List[ThemeView] = Field(default_factory=list)


class CompanyAnalysisList(BaseModel):
    companies: List[CompanyAnalysis] = Field(default_factory=list)


class EducationalContent(BaseModel):
    learn_one_thing: LearnOneThing
    terminology: List[TerminologyTerm] = Field(default_factory=list)


class EditorialSynthesis(BaseModel):
    three_things_that_matter: List[str] = Field(default_factory=list)
    main_risk_today: str
    one_sentence_summary: str
    dominant_narrative: str
    mental_model: MentalModel
