"""MacroProvider abstract interface (Section 27)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import List

from src.models.schemas import MacroEvent


class MacroProvider(ABC):
    """Real implementations: FRED (releases calendar), BLS, BEA, official
    government calendars. Returns the day's macro calendar plus any
    just-released data points."""

    name: str = "base"

    @abstractmethod
    def get_calendar(self, run_date: date) -> List[MacroEvent]:
        raise NotImplementedError
