"""HTML report rendering (Section 23) via Jinja2."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.models.schemas import MorningReport
from src.utils.time import to_sgt

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _badge_class(value: str) -> str:
    v = (value or "").upper()
    if "BULLISH" in v or v in ("LONG WATCH", "IMPROVING", "RISK_ON", "AI_LED", "GROWTH_LED"):
        return "badge-bullish"
    if "BEARISH" in v or v in ("SHORT WATCH", "DETERIORATING", "RISK_OFF"):
        return "badge-bearish"
    if v in ("NEUTRAL", "UNCHANGED", "AVOID", "NO TRADE", "MIXED"):
        return "badge-neutral"
    return "badge-neutral"


def _fmt_pct(value) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def get_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["pct"] = _fmt_pct
    env.filters["badge_class"] = _badge_class
    env.filters["sgt"] = lambda dt, fmt="%H:%M %Z": to_sgt(dt).strftime(fmt) if dt else "—"
    return env


def render_report(report: MorningReport) -> str:
    env = get_env()
    template = env.get_template("morning_email.html")
    return template.render(report=report)


def render_report_pdf_html(report: MorningReport) -> str:
    """Render the compact, print-optimized layout (A4, ~3-5 pages) used as
    the source for PDF export - see src/reports/pdf.py::html_to_pdf()."""
    env = get_env()
    template = env.get_template("morning_pdf.html")
    return template.render(report=report)
