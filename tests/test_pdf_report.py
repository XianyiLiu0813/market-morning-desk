"""PDF report generation tests.

Skipped automatically when no Chrome/Chromium install is found (e.g. a CI
runner without a browser) - PDF delivery is an optional enhancement on top
of the core HTML pipeline, not a hard dependency for the rest of the test
suite (see conftest.py, which defaults EMAIL_FORMAT=html for all other
tests so they stay fast/portable).
"""
from __future__ import annotations

import pytest

from src.reports.pdf import ChromeNotFoundError, find_chrome, html_to_pdf
from src.reports.renderer import render_report, render_report_pdf_html
from src.models.schemas import MorningReport

pytestmark = pytest.mark.skipif(find_chrome() is None, reason="No Chrome/Chromium install found")


def test_pdf_template_renders_without_error(minimal_report_kwargs):
    report = MorningReport(**minimal_report_kwargs)
    html = render_report_pdf_html(report)
    assert "AI Market Morning Desk" in html
    assert "@page" in html  # print-specific CSS (A4 sizing) must be present


def test_html_to_pdf_produces_valid_pdf_file(minimal_report_kwargs, tmp_path):
    report = MorningReport(**minimal_report_kwargs)
    html = render_report_pdf_html(report)
    out_path = str(tmp_path / "report.pdf")
    result_path = html_to_pdf(html, out_path)
    assert result_path == out_path

    from pypdf import PdfReader

    reader = PdfReader(out_path)
    assert len(reader.pages) >= 1


def test_pdf_page_count_within_target_range_for_realistic_report(tmp_path):
    """A realistic MOCK_MODE report should render to roughly 3-5 pages,
    matching the product's target reading time (Section 24)."""
    import os
    from datetime import date

    from src.pipeline import run_morning_pipeline
    from src.utils.config import get_settings

    os.environ["MOCK_MODE"] = "true"
    settings = get_settings(force_reload=True)
    settings.db_path = str(tmp_path / "pdf_test.db")

    result = run_morning_pipeline(
        run_date=date(2026, 9, 9), settings=settings, send_email=False, output_dir=str(tmp_path / "outbox"),
    )
    report = result["report"]

    html = render_report_pdf_html(report)
    out_path = str(tmp_path / "report.pdf")
    html_to_pdf(html, out_path)

    from pypdf import PdfReader

    reader = PdfReader(out_path)
    # Generous bounds - the exact count depends on how much content the
    # mock analysis produces, but it should never balloon far past target.
    assert 1 <= len(reader.pages) <= 8


def test_chrome_not_found_error_is_raised_cleanly(monkeypatch, minimal_report_kwargs):
    import src.reports.pdf as pdf_module

    monkeypatch.setattr(pdf_module, "find_chrome", lambda: None)
    report = MorningReport(**minimal_report_kwargs)
    html = render_report_pdf_html(report)
    with pytest.raises(ChromeNotFoundError):
        pdf_module.html_to_pdf(html, "/tmp/should_not_be_created.pdf")


def test_pipeline_falls_back_to_html_when_chrome_missing(monkeypatch, tmp_path):
    """Even with EMAIL_FORMAT=pdf configured, a missing Chrome install must
    not crash the pipeline - it should log a warning and fall back to
    sending the full HTML report instead (Section 27: one non-critical
    provider/tool failing should not break the run)."""
    import os
    from datetime import date

    import src.reports.pdf as pdf_module
    from src.pipeline import run_morning_pipeline
    from src.utils.config import get_settings

    monkeypatch.setattr(pdf_module, "find_chrome", lambda: None)
    os.environ["MOCK_MODE"] = "true"
    os.environ["EMAIL_FORMAT"] = "pdf"
    settings = get_settings(force_reload=True)
    settings.db_path = str(tmp_path / "pdf_fallback_test.db")
    settings.email_format = "pdf"

    result = run_morning_pipeline(
        run_date=date(2026, 9, 9), settings=settings, send_email=False, output_dir=str(tmp_path / "outbox"),
    )
    assert result["email_status"] == "skipped"
    assert result["email_path"].endswith(".html")
    os.environ["EMAIL_FORMAT"] = "html"
