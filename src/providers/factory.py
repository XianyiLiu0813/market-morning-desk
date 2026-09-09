"""Provider factory: wires up the configured provider for each interface,
falling back to mock when required API keys/config are missing (Section 27).

This is the ONLY place that should decide "which concrete provider class to
instantiate" - collectors and analysis modules only ever see the abstract
interfaces.
"""
from __future__ import annotations

import logging
import os
from typing import List

from src.providers.email_base import EmailProvider
from src.providers.llm_base import LLMProvider
from src.providers.macro_base import MacroProvider
from src.providers.market_base import MarketDataProvider
from src.providers.mock_providers import (
    MockEmailProvider,
    MockLLMProvider,
    MockMacroProvider,
    MockMarketDataProvider,
    MockNewsProvider,
)
from src.providers.news_base import NewsProvider
from src.utils.config import Settings

logger = logging.getLogger("morning_desk")


def build_market_provider(settings: Settings) -> MarketDataProvider:
    if settings.mock_mode:
        return MockMarketDataProvider()
    try:
        from src.providers.real_market import YFinanceMarketDataProvider

        return YFinanceMarketDataProvider()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falling back to mock market data provider: %s", exc)
        return MockMarketDataProvider()


def build_news_providers(settings: Settings) -> List[NewsProvider]:
    if settings.mock_mode:
        return [MockNewsProvider()]

    providers: List[NewsProvider] = []
    try:
        from src.providers.real_news import NewsApiProvider, RssNewsProvider

        newsapi_key = os.environ.get("NEWSAPI_KEY")
        if newsapi_key:
            providers.append(NewsApiProvider(api_key=newsapi_key))

        for tier, tier_cfg in settings.source_tiers.items():
            for src in tier_cfg.get("sources", []):
                if src.get("kind") == "rss" and src.get("url"):
                    providers.append(
                        RssNewsProvider(
                            source_id=src["id"],
                            source_name=src["name"],
                            feed_url=src["url"],
                            tier=int(tier),
                        )
                    )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error constructing real news providers: %s", exc)

    if not providers:
        logger.warning("No real news providers configured; falling back to mock news provider.")
        providers = [MockNewsProvider()]
    return providers


def build_macro_provider(settings: Settings) -> MacroProvider:
    if settings.mock_mode:
        return MockMacroProvider()
    fred_key = os.environ.get("FRED_API_KEY")
    if fred_key:
        try:
            from src.providers.real_macro import FredMacroProvider

            return FredMacroProvider(api_key=fred_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falling back to mock macro provider: %s", exc)
    else:
        logger.info("FRED_API_KEY not set; using mock macro calendar.")
    return MockMacroProvider()


def build_llm_provider(settings: Settings) -> LLMProvider:
    provider_name = settings.llm_provider.lower()
    if provider_name == "mock" or settings.mock_mode:
        return MockLLMProvider()

    if provider_name == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set; using mock LLM.")
            return MockLLMProvider()
        from src.providers.real_llm import AnthropicLLMProvider

        return AnthropicLLMProvider(api_key=api_key, model=settings.llm_model)

    if provider_name == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("LLM_PROVIDER=openai but OPENAI_API_KEY is not set; using mock LLM.")
            return MockLLMProvider()
        from src.providers.real_llm import OpenAILLMProvider

        return OpenAILLMProvider(api_key=api_key, model=settings.llm_model)

    logger.warning("Unknown LLM_PROVIDER '%s'; using mock LLM.", provider_name)
    return MockLLMProvider()


def build_email_provider(settings: Settings) -> EmailProvider:
    provider_name = settings.email_provider.lower()
    if provider_name == "mock" or settings.mock_mode:
        return MockEmailProvider()

    if provider_name == "resend":
        api_key = os.environ.get("RESEND_API_KEY")
        if not api_key:
            logger.warning("EMAIL_PROVIDER=resend but RESEND_API_KEY is not set; using mock email provider.")
            return MockEmailProvider()
        from src.providers.real_email import ResendEmailProvider

        return ResendEmailProvider(api_key=api_key)

    if provider_name == "smtp":
        host = os.environ.get("SMTP_HOST")
        if not host:
            logger.warning("EMAIL_PROVIDER=smtp but SMTP_HOST is not set; using mock email provider.")
            return MockEmailProvider()
        from src.providers.real_email import SmtpEmailProvider

        return SmtpEmailProvider(
            host=host,
            port=int(os.environ.get("SMTP_PORT", "587")),
            username=os.environ.get("SMTP_USERNAME", ""),
            password=os.environ.get("SMTP_PASSWORD", ""),
            use_tls=os.environ.get("SMTP_USE_TLS", "true").lower() == "true",
        )

    logger.warning("Unknown EMAIL_PROVIDER '%s'; using mock email provider.", provider_name)
    return MockEmailProvider()
