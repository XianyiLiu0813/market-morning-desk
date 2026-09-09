"""Macro calendar collection orchestration (Section 7)."""
from __future__ import annotations

import logging
from datetime import date
from typing import List

from src.models.schemas import MacroEvent
from src.providers.macro_base import MacroProvider

logger = logging.getLogger("morning_desk")


def collect_macro_calendar(provider: MacroProvider, run_date: date) -> List[MacroEvent]:
    try:
        events = provider.get_calendar(run_date)
        logger.info("Macro provider '%s' returned %d event(s)", provider.name, len(events))
        return events
    except Exception as exc:  # noqa: BLE001
        logger.warning("Macro provider '%s' failed, continuing without macro calendar: %s", provider.name, exc)
        return []
