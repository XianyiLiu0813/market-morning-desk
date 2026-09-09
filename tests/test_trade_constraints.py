"""Trade setup constraint tests (Section 35: no-more-than-max trade ideas,
zero allowed)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.analysis.trade_analysis import generate_trade_ideas
from src.models.schemas import MorningReport, TradeIdea
from src.providers.mock_providers import MockLLMProvider


def test_generate_trade_ideas_respects_max_ideas():
    llm = MockLLMProvider()
    themes = []
    companies = []
    ideas = generate_trade_ideas(llm, themes, companies, max_ideas=3)
    assert len(ideas) <= 3


def test_generate_trade_ideas_empty_inputs_returns_empty_list():
    llm = MockLLMProvider()
    ideas = generate_trade_ideas(llm, [], [], max_ideas=3)
    assert ideas == []


def test_morning_report_rejects_more_than_three_trade_ideas(minimal_report_kwargs):
    kwargs = dict(minimal_report_kwargs)
    kwargs["trade_ideas"] = [
        TradeIdea(direction="LONG WATCH"),
        TradeIdea(direction="LONG WATCH"),
        TradeIdea(direction="LONG WATCH"),
        TradeIdea(direction="LONG WATCH"),
    ]
    with pytest.raises(ValidationError):
        MorningReport(**kwargs)


def test_morning_report_allows_zero_trade_ideas(minimal_report_kwargs):
    kwargs = dict(minimal_report_kwargs)
    kwargs["trade_ideas"] = []
    report = MorningReport(**kwargs)
    assert report.trade_ideas == []
