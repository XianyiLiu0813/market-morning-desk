"""HTML report rendering (Section 23) via Jinja2."""
from __future__ import annotations

import math
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
    if v in ("NEUTRAL", "UNCHANGED", "AVOID", "NO TRADE", "WAIT", "MIXED"):
        return "badge-neutral"
    return "badge-neutral"


def _is_missing(value) -> bool:
    """True for None and for NaN/inf - the schema-level guard should already
    prevent NaN from reaching here, but the renderer must never trust that
    blindly (P0: a report must NEVER show "nan%")."""
    if value is None:
        return True
    try:
        return math.isnan(value) or math.isinf(value)
    except TypeError:
        return False


def _fmt_pct(value) -> str:
    if _is_missing(value):
        return "数据暂缺"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _fmt_bp(asset) -> str:
    """Render a rate-type MarketAsset's basis-point change, e.g. '+7bp'."""
    bp = asset.bp_change if hasattr(asset, "bp_change") else None
    if _is_missing(bp):
        return "数据暂缺"
    sign = "+" if bp > 0 else ""
    return f"{sign}{bp:.1f}bp"


def _fmt_level(value, decimals: int = 2) -> str:
    if _is_missing(value):
        return "数据暂缺"
    return f"{value:.{decimals}f}"


def get_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["pct"] = _fmt_pct
    env.filters["bp"] = _fmt_bp
    env.filters["level"] = _fmt_level
    env.filters["badge_class"] = _badge_class
    env.filters["sgt"] = lambda dt, fmt="%H:%M %Z": to_sgt(dt).strftime(fmt) if dt else "—"
    env.tests["missing"] = _is_missing
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
