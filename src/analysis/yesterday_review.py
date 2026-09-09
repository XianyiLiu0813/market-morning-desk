"""Yesterday's calls review (Section 22) - optional, toggled by
settings.yesterday_review.

Tracks prior trade_ideas rows and, when market data allows, computes the
subsequent move. Explicitly does NOT claim a call was "correct" just
because price moved in the predicted direction - it separates thesis
quality (was the reasoning sound) from outcome (what price actually did).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import select

from src.models.database import TradeIdeaRow, get_session
from src.models.schemas import MarketAsset, TradeDirection, YesterdayReviewItem


def get_prior_trade_ideas(run_date: date, lookback_days: int = 5) -> List[TradeIdeaRow]:
    earliest = run_date - timedelta(days=lookback_days)
    with get_session() as session:
        rows = (
            session.execute(
                select(TradeIdeaRow)
                .where(TradeIdeaRow.run_date >= earliest, TradeIdeaRow.run_date < run_date)
                .order_by(TradeIdeaRow.run_date.desc())
            )
            .scalars()
            .all()
        )
        # Detach values we need before the session closes.
        return [
            TradeIdeaRow(
                id=r.id,
                run_date=r.run_date,
                ticker=r.ticker,
                direction=r.direction,
                thesis=r.thesis,
                invalidation_condition=r.invalidation_condition,
                reference_price=r.reference_price,
                confidence_pct=r.confidence_pct,
            )
            for r in rows
        ]


def build_review(
    prior_ideas: List[TradeIdeaRow], assets_by_symbol: dict
) -> List[YesterdayReviewItem]:
    out: List[YesterdayReviewItem] = []
    for idea in prior_ideas:
        if not idea.ticker:
            continue
        current: Optional[MarketAsset] = assets_by_symbol.get(idea.ticker)
        subsequent_move = None
        thesis_intact = None
        if current and idea.reference_price and current.last_price:
            subsequent_move = round(
                (current.last_price - idea.reference_price) / idea.reference_price * 100, 2
            )
            if idea.direction == TradeDirection.LONG_WATCH.value:
                thesis_intact = subsequent_move >= 0
            elif idea.direction == TradeDirection.SHORT_WATCH.value:
                thesis_intact = subsequent_move <= 0

        lesson = (
            "价格朝预期方向移动了，但这本身并不能证明当初的逻辑是对的——需要回头核实一下最初设想的催化剂"
            "是否真的按预期兑现了。"
            if thesis_intact
            else "目前的走势还没有（或没能）验证最初的判断方向；建议回顾一下失效条件是否已经触发，"
            "还是只是需要更多时间/确认。"
            if thesis_intact is False
            else "现有行情数据不足以评估这个想法的结果。"
        )

        out.append(
            YesterdayReviewItem(
                ticker=idea.ticker,
                direction=TradeDirection(idea.direction),
                original_thesis=idea.thesis or "",
                reference_price=idea.reference_price,
                subsequent_move_pct=subsequent_move,
                max_favorable_excursion_pct=None,
                max_adverse_excursion_pct=None,
                thesis_intact=thesis_intact,
                lesson=lesson,
            )
        )
    return out
