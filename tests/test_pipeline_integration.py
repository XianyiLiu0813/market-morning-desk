"""End-to-end mock pipeline integration test (Section 35/47 acceptance
criteria): the full pipeline must run start-to-finish with zero external
API keys when MOCK_MODE=true."""
from __future__ import annotations

from datetime import date


def test_full_mock_pipeline_runs_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test_run.db"))
    monkeypatch.delenv("EMAIL_TO", raising=False)

    from src.pipeline import run_morning_pipeline
    from src.utils.config import get_settings

    settings = get_settings(force_reload=True)
    settings.db_path = str(tmp_path / "test_run.db")

    result = run_morning_pipeline(
        run_date=date(2026, 9, 9), settings=settings, send_email=False, output_dir=str(tmp_path / "outbox"),
    )

    report = result["report"]
    assert report.run_date == date(2026, 9, 9)
    assert len(report.market_snapshot.assets) > 0
    assert len(report.top_stories) > 0 or len(report.macro_stories) > 0
    assert len(report.trade_ideas) <= 3
    assert len(report.three_things_that_matter) == 3
    assert report.learn_one_thing is not None
    assert "<!DOCTYPE html>" in result["html"]
    assert result["email_status"] == "skipped"


def test_pipeline_persists_run_to_database(tmp_path, monkeypatch):
    from sqlalchemy import select

    from src.models.database import ReportRow, SystemRunRow, get_session
    from src.pipeline import run_morning_pipeline
    from src.utils.config import get_settings

    monkeypatch.setenv("MOCK_MODE", "true")
    settings = get_settings(force_reload=True)
    settings.db_path = str(tmp_path / "test_run2.db")

    result = run_morning_pipeline(
        run_date=date(2026, 9, 10), settings=settings, send_email=False, output_dir=str(tmp_path / "outbox"),
    )

    with get_session() as session:
        run_row = session.execute(select(SystemRunRow).where(SystemRunRow.run_id == result["run_id"])).scalar_one()
        assert run_row.status in ("success", "degraded")
        report_row = session.execute(select(ReportRow).where(ReportRow.run_date == date(2026, 9, 10))).scalar_one()
        assert report_row.json_payload
