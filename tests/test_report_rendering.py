"""Report rendering tests (Section 35)."""
from __future__ import annotations

from src.models.schemas import MorningReport, TradeIdea
from src.reports.renderer import render_report


def test_render_report_produces_valid_html_skeleton(minimal_report_kwargs):
    report = MorningReport(**minimal_report_kwargs)
    html = render_report(report)
    assert "<!DOCTYPE html>" in html
    assert "AI Market Morning Desk" in html
    assert "not financial advice" in html


def test_render_report_shows_no_trade_box_when_no_ideas(minimal_report_kwargs):
    kwargs = dict(minimal_report_kwargs)
    kwargs["trade_ideas"] = []
    report = MorningReport(**kwargs)
    html = render_report(report)
    assert "NO HIGH-CONVICTION SETUP TODAY" in html


def test_render_report_shows_trade_idea_when_present(minimal_report_kwargs):
    kwargs = dict(minimal_report_kwargs)
    kwargs["trade_ideas"] = [TradeIdea(ticker="NVDA", direction="LONG WATCH", thesis="Test thesis")]
    report = MorningReport(**kwargs)
    html = render_report(report)
    assert "NVDA" in html
    assert "Test thesis" in html
    assert "NO HIGH-CONVICTION SETUP TODAY" not in html


def test_render_report_shows_degraded_mode_warning(minimal_report_kwargs):
    from src.models.schemas import DataQualityStatus

    kwargs = dict(minimal_report_kwargs)
    kwargs["data_quality"] = DataQualityStatus(ok=False, degraded_mode=True, reasons=["Test reason"])
    report = MorningReport(**kwargs)
    html = render_report(report)
    assert "DATA QUALITY WARNING" in html
    assert "Test reason" in html


def test_render_report_escapes_html_in_story_content(minimal_report_kwargs):
    from src.models.schemas import ImportanceLevel, StoryAnalysis

    kwargs = dict(minimal_report_kwargs)
    kwargs["top_stories"] = [
        StoryAnalysis(
            cluster_id="c1",
            title="<script>alert(1)</script>",
            importance=ImportanceLevel.HIGH,
            fact="fact",
            why_it_matters="why",
        )
    ]
    report = MorningReport(**kwargs)
    html = render_report(report)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
