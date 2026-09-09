"""HTML -> PDF conversion for the compact "3-5 page" PDF report delivery
mode.

Uses a local headless Chrome/Chromium install (no extra Python dependency
needed - reportlab/weasyprint pull in heavier system deps). If no Chrome
install is found, `html_to_pdf` raises `ChromeNotFoundError` so callers can
decide how to degrade (e.g. fall back to emailing the HTML report instead
of failing the whole run).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("morning_desk")

# Common install locations across macOS / Linux / CI runners, in preference
# order. `CHROME_PATH` env var (if set) is checked first by find_chrome().
_CANDIDATE_PATHS: List[str] = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
]


class ChromeNotFoundError(RuntimeError):
    pass


def find_chrome() -> Optional[str]:
    import os

    env_path = os.environ.get("CHROME_PATH")
    if env_path and (Path(env_path).exists() or shutil.which(env_path)):
        return env_path
    for candidate in _CANDIDATE_PATHS:
        if candidate.startswith("/"):
            if Path(candidate).exists():
                return candidate
        else:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
    return None


def html_to_pdf(html: str, output_path: str, timeout: int = 60) -> str:
    """Render `html` to a PDF file at `output_path` via headless Chrome.
    Returns output_path on success. Raises ChromeNotFoundError if no Chrome/
    Chromium install can be located."""
    chrome = find_chrome()
    if not chrome:
        raise ChromeNotFoundError(
            "No Chrome/Chromium install found (checked CHROME_PATH env var and "
            "common install locations). Install Google Chrome, or set CHROME_PATH "
            "to a Chrome/Chromium binary, to enable PDF report generation."
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        html_path = f.name

    try:
        result = subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-extensions",
                f"--print-to-pdf={output_path}",
                "--no-pdf-header-footer",
                "--print-to-pdf-no-header",
                f"file://{html_path}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0 or not Path(output_path).exists():
            logger.error("Chrome PDF export failed (rc=%s): %s", result.returncode, result.stderr[-2000:])
            raise RuntimeError(f"Chrome PDF export failed: {result.stderr[-500:]}")
        return output_path
    finally:
        try:
            Path(html_path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
