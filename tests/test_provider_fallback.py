"""Missing/failing provider handling tests (Section 27/33/35) - one
provider failing must not crash the pipeline."""
from __future__ import annotations

from datetime import date

from src.collectors.macro import collect_macro_calendar
from src.collectors.market import collect_market_snapshot
from src.collectors.news import collect_articles
from src.providers.macro_base import MacroProvider
from src.providers.market_base import MarketDataProvider
from src.providers.news_base import NewsProvider


class AlwaysFailsMarketProvider(MarketDataProvider):
    name = "broken_market"

    def get_snapshot(self, symbols):
        raise ConnectionError("simulated outage")


class AlwaysFailsNewsProvider(NewsProvider):
    name = "broken_news"
    tier = 2

    def fetch(self, since_hours=18):
        raise TimeoutError("simulated timeout")


class AlwaysFailsMacroProvider(MacroProvider):
    name = "broken_macro"

    def get_calendar(self, run_date):
        raise RuntimeError("simulated failure")


def test_market_provider_failure_does_not_raise(settings):
    snapshot = collect_market_snapshot(AlwaysFailsMarketProvider(), settings, date(2026, 9, 9))
    assert snapshot.assets == []
    assert any("failed" in w.lower() for w in snapshot.warnings)


def test_news_provider_failure_does_not_raise():
    articles = collect_articles([AlwaysFailsNewsProvider()])
    assert articles == []


def test_one_news_provider_failing_does_not_block_others():
    from src.providers.mock_providers import MockNewsProvider

    articles = collect_articles([AlwaysFailsNewsProvider(), MockNewsProvider()])
    assert len(articles) > 0


def test_macro_provider_failure_does_not_raise():
    events = collect_macro_calendar(AlwaysFailsMacroProvider(), date(2026, 9, 9))
    assert events == []


def test_factory_falls_back_to_mock_when_llm_key_missing(monkeypatch, settings):
    from src.providers.factory import build_llm_provider

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings.mock_mode = False
    settings.llm_provider = "anthropic"
    provider = build_llm_provider(settings)
    assert provider.name == "mock"


def test_factory_falls_back_to_mock_when_email_key_missing(monkeypatch, settings):
    from src.providers.factory import build_email_provider

    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    settings.mock_mode = False
    settings.email_provider = "resend"
    provider = build_email_provider(settings)
    assert provider.name == "mock"
