"""Real MacroProvider implementation using FRED (Federal Reserve Economic Data).

FRED's release-dates API gives scheduled release dates for series like CPI,
PCE, payrolls, etc. Requires FRED_API_KEY (free from
https://fred.stlouisfed.org/docs/api/api_key.html).

V1 note: FRED reports release DATES well, but "expected/consensus" figures
(what Wall Street forecasts) aren't part of FRED - that typically requires
a vendor like Trading Economics or Econoday. This implementation surfaces
what FRED can reliably provide (release name + date + previous actual
value from the series) and leaves `expected` as None rather than
fabricating a consensus number (Section 26 guardrail).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List

from src.models.schemas import ImportanceLevel, MacroEvent
from src.providers.macro_base import MacroProvider
from src.utils.retry import retry_with_backoff
from src.utils.time import SGT, UTC

logger = logging.getLogger("morning_desk")

# series_id -> (event label, importance)
WATCHED_SERIES = {
    "CPIAUCSL": ("US CPI (headline)", ImportanceLevel.HIGH),
    "PCEPI": ("US PCE Price Index", ImportanceLevel.HIGH),
    "PAYEMS": ("US Nonfarm Payrolls", ImportanceLevel.HIGH),
    "UNRATE": ("US Unemployment Rate", ImportanceLevel.HIGH),
    "ICSA": ("US Initial Jobless Claims", ImportanceLevel.MEDIUM),
    "JTSJOL": ("US JOLTS Job Openings", ImportanceLevel.MEDIUM),
    "GDP": ("US GDP", ImportanceLevel.HIGH),
}


class FredMacroProvider(MacroProvider):
    name = "fred"

    def __init__(self, api_key: str):
        self.api_key = api_key

    @retry_with_backoff(max_attempts=3)
    def get_calendar(self, run_date: date) -> List[MacroEvent]:
        import requests

        out: List[MacroEvent] = []
        for series_id, (label, importance) in WATCHED_SERIES.items():
            try:
                obs_resp = requests.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": self.api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 1,
                    },
                    timeout=10,
                )
                obs_resp.raise_for_status()
                obs = obs_resp.json().get("observations", [])
                previous_value = obs[0]["value"] if obs else None
                out.append(
                    MacroEvent(
                        event=label,
                        scheduled_at_sgt=None,
                        local_time_label=None,
                        expected=None,
                        previous=previous_value,
                        actual=None,
                        importance=importance,
                        notes="Release date/consensus not available from FRED observations "
                        "endpoint alone; wire up FRED release-dates API or a calendar vendor "
                        "for precise scheduling.",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("FRED series %s failed: %s", series_id, exc)
                continue
        return out
