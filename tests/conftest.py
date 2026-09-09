"""Shared pytest fixtures."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("MOCK_MODE", "true")


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    """Ensure each test gets a fresh Settings() reflecting current env vars,
    since get_settings() caches a module-level singleton."""
    from src.utils import config as config_module

    config_module._settings_singleton = None
    yield
    config_module._settings_singleton = None


@pytest.fixture()
def settings():
    from src.utils.config import get_settings

    return get_settings(force_reload=True)


@pytest.fixture()
def minimal_report_kwargs():
    """Minimal valid kwargs to construct a MorningReport in tests, covering
    every field without a default."""
    from datetime import date, datetime, timezone as tz

    from src.models.schemas import MarketRegimeView, MarketSnapshot

    return dict(
        run_date=date(2026, 9, 9),
        generated_at=datetime.now(tz=tz.utc),
        timezone="Asia/Singapore",
        regime=MarketRegimeView(
            labels=["MIXED"], confidence_pct=50, summary="test", supporting_evidence=[],
            contradicting_evidence=[], source_ids=[],
        ),
        market_snapshot=MarketSnapshot(
            run_date=date(2026, 9, 9), generated_at=datetime.now(tz=tz.utc), assets=[], warnings=[],
        ),
    )


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Initialize a fresh throwaway SQLite DB for tests that touch the DB."""
    from src.models import database as db_module

    db_path = tmp_path / "test.db"
    db_module.init_db(str(db_path))
    return db_path
