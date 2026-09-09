"""Mock providers used when MOCK_MODE=true (Section 35/36).

These read the fixtures in tests/fixtures/ so the full pipeline can be
demonstrated and tested with zero external API keys. Also handy as a
reference for what a real provider's return shape should look like.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from src.models.schemas import MacroEvent, MarketAsset, NewsArticle, SourceTier
from src.providers.email_base import EmailProvider
from src.providers.llm_base import LLMProvider
from src.providers.macro_base import MacroProvider
from src.providers.market_base import MarketDataProvider
from src.providers.news_base import NewsProvider
from src.utils.time import now_sgt, now_utc

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


class MockMarketDataProvider(MarketDataProvider):
    name = "mock"

    def __init__(self, fixture_path: Path = FIXTURES_DIR / "mock_market.json"):
        with open(fixture_path, "r", encoding="utf-8") as f:
            self._data: Dict[str, Any] = json.load(f)

    def get_snapshot(self, symbols: List[str]) -> List[MarketAsset]:
        out: List[MarketAsset] = []
        as_of = now_utc()
        for sym in symbols:
            row = self._data.get(sym)
            if row is None:
                continue
            out.append(
                MarketAsset(
                    symbol=sym,
                    display_name=row["display"],
                    group=row["group"],
                    previous_close=row.get("previous_close"),
                    last_price=row.get("last_price"),
                    daily_pct=row.get("daily_pct"),
                    overnight_pct=row.get("overnight_pct"),
                    volume=row.get("volume"),
                    relative_volume=row.get("relative_volume"),
                    return_5d_pct=row.get("return_5d_pct"),
                    return_1m_pct=row.get("return_1m_pct"),
                    pct_from_52w_high=row.get("pct_from_52w_high"),
                    as_of=as_of,
                    data_source="mock",
                    is_stale=False,
                )
            )
        return out


class MockNewsProvider(NewsProvider):
    name = "mock"
    tier = 2

    def __init__(self, fixture_path: Path = FIXTURES_DIR / "mock_news.json"):
        with open(fixture_path, "r", encoding="utf-8") as f:
            self._data: List[Dict[str, Any]] = json.load(f)

    def fetch(self, since_hours: int = 18) -> List[NewsArticle]:
        now = now_utc()
        out: List[NewsArticle] = []
        for row in self._data:
            hours_ago = row.get("published_at_hours_ago", 12)
            if hours_ago > since_hours:
                continue
            published_at = now - timedelta(hours=hours_ago)
            out.append(
                NewsArticle(
                    article_id=row["article_id"],
                    title=row["title"],
                    summary=row.get("summary"),
                    body_excerpt=row.get("body_excerpt"),
                    url=row.get("url"),
                    source_id=row["source_id"],
                    source_name=row["source_name"],
                    tier=SourceTier(row["tier"]),
                    published_at=published_at,
                    tickers=row.get("tickers", []),
                    themes=row.get("themes", []),
                )
            )
        return out


class MockMacroProvider(MacroProvider):
    name = "mock"

    def __init__(self, fixture_path: Path = FIXTURES_DIR / "mock_macro.json"):
        with open(fixture_path, "r", encoding="utf-8") as f:
            self._data: List[Dict[str, Any]] = json.load(f)

    def get_calendar(self, run_date) -> List[MacroEvent]:
        out: List[MacroEvent] = []
        for row in self._data:
            scheduled = datetime.combine(run_date, datetime.min.time()).replace(
                hour=row.get("hour_sgt", 9), minute=row.get("minute_sgt", 0)
            )
            out.append(
                MacroEvent(
                    event=row["event"],
                    scheduled_at_sgt=scheduled,
                    local_time_label=row.get("local_time_label"),
                    expected=row.get("expected"),
                    previous=row.get("previous"),
                    actual=row.get("actual"),
                    importance=row.get("importance", "MEDIUM"),
                    notes=row.get("notes"),
                )
            )
        return out


class MockEmailProvider(EmailProvider):
    """Writes the email to disk instead of sending it, so MOCK_MODE never
    requires real credentials. Path is logged/returned for inspection."""

    name = "mock"

    def __init__(self, output_dir: str = "outbox"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.last_path: Path | None = None
        self.last_attachment_paths: list = []

    def send(self, to_addr, from_addr, subject, html_body, attachments=None) -> bool:
        ts = now_sgt().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"mock_email_{ts}.html"
        path.write_text(html_body, encoding="utf-8")
        self.last_path = path
        self.last_attachment_paths = []
        for att in attachments or []:
            att_path = self.output_dir / f"mock_email_{ts}_{att.filename}"
            att_path.write_bytes(att.content)
            self.last_attachment_paths.append(att_path)
        return True


class MockLLMProvider(LLMProvider):
    """Deterministic canned-response LLM used for tests and demonstrations.

    Rather than trying to fake a general chat model, this returns
    hand-crafted, schema-valid JSON keyed by a `task` marker embedded in the
    system prompt by each analysis module (see src/analysis/*.py). This
    keeps MOCK_MODE fully offline while still exercising the full
    validation path (Pydantic parses these exactly like a real LLM
    response).
    """

    name = "mock"

    def __init__(self):
        self._last_usage = {"input_tokens": 0, "output_tokens": 0}

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> str:
        self._last_usage = {
            "input_tokens": len(system_prompt.split()) + len(user_prompt.split()),
            "output_tokens": 0,
        }
        task = _extract_task(system_prompt)
        from src.providers.mock_llm_responses import get_mock_response

        response = get_mock_response(task, user_prompt)
        self._last_usage["output_tokens"] = len(json.dumps(response).split())
        return json.dumps(response)

    def last_usage(self):
        return self._last_usage


def _extract_task(system_prompt: str) -> str:
    marker = "TASK:"
    if marker in system_prompt:
        line = [l for l in system_prompt.splitlines() if marker in l][0]
        return line.split(marker, 1)[1].strip()
    return "unknown"
