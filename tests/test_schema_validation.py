"""JSON schema validation tests (Section 26/35) - the LLM call wrapper must
reject invalid output rather than let it flow into the report."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.analysis.llm_client import call_llm_json
from src.models.schemas import MarketRegimeView, TradeIdea, TradeIdeaList
from src.providers.llm_base import LLMProvider


class FixedResponseLLM(LLMProvider):
    name = "fixed"

    def __init__(self, raw: str):
        self.raw = raw

    def generate_json(self, system_prompt, user_prompt, max_tokens=4096, temperature=0.2):
        return self.raw


def test_valid_json_validates_successfully():
    payload = {
        "labels": ["RISK_ON"],
        "confidence_pct": 70,
        "summary": "Broad rally.",
        "supporting_evidence": [],
        "contradicting_evidence": [],
        "source_ids": [],
    }
    llm = FixedResponseLLM(json.dumps(payload))
    result = call_llm_json(llm, "market_regime", "instructions", {}, MarketRegimeView)
    assert result is not None
    assert result.confidence_pct == 70


def test_invalid_json_returns_none_not_raise():
    llm = FixedResponseLLM("this is not valid json {{{")
    result = call_llm_json(llm, "market_regime", "instructions", {}, MarketRegimeView)
    assert result is None


def test_schema_mismatch_returns_none_not_raise():
    # confidence_pct out of range (0-100) should fail validation.
    payload = {
        "labels": ["RISK_ON"],
        "confidence_pct": 250,
        "summary": "Broad rally.",
        "supporting_evidence": [],
        "contradicting_evidence": [],
        "source_ids": [],
    }
    llm = FixedResponseLLM(json.dumps(payload))
    result = call_llm_json(llm, "market_regime", "instructions", {}, MarketRegimeView)
    assert result is None


def test_llm_exception_returns_none_not_raise():
    class ExplodingLLM(LLMProvider):
        name = "exploding"

        def generate_json(self, *args, **kwargs):
            raise ConnectionError("network down")

    result = call_llm_json(ExplodingLLM(), "market_regime", "instructions", {}, MarketRegimeView)
    assert result is None


def test_trade_idea_list_rejects_more_than_three():
    with pytest.raises(ValidationError):
        TradeIdeaList(
            ideas=[
                TradeIdea(direction="LONG WATCH"),
                TradeIdea(direction="LONG WATCH"),
                TradeIdea(direction="LONG WATCH"),
                TradeIdea(direction="LONG WATCH"),
            ]
        )


def test_trade_idea_list_allows_zero_ideas():
    tl = TradeIdeaList(ideas=[])
    assert tl.ideas == []
