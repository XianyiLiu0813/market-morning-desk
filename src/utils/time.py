"""Timezone helpers.

The whole product reasons in Asia/Singapore time (Section 3), but market
data/news timestamps arrive in UTC or exchange-local time. Centralize
conversions here so every module treats time consistently.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

SGT = ZoneInfo("Asia/Singapore")
UTC = timezone.utc
US_EASTERN = ZoneInfo("America/New_York")
HK_TIME = ZoneInfo("Asia/Hong_Kong")


def now_sgt() -> datetime:
    return datetime.now(tz=SGT)


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def to_sgt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(SGT)


def parse_run_date(date_str: Optional[str]) -> date:
    """Parse a --date YYYY-MM-DD CLI argument, default to today in SGT."""
    if not date_str:
        return now_sgt().date()
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def fmt_sgt(dt: datetime, fmt: str = "%Y-%m-%d %H:%M %Z") -> str:
    return to_sgt(dt).strftime(fmt)


def age_minutes(dt: datetime, reference: Optional[datetime] = None) -> float:
    ref = reference or now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=UTC)
    return (ref - dt).total_seconds() / 60.0


def sgt_to_utc_cron(hour: int, minute: int) -> str:
    """Convert an Asia/Singapore HH:MM (no DST) to a UTC cron 'm h * * *' string.

    Singapore is fixed UTC+8 year-round (no DST), so this is a static offset
    subtraction. Used to document/generate the GitHub Actions cron schedule.
    """
    total_minutes = hour * 60 + minute - 8 * 60
    total_minutes %= 24 * 60
    utc_hour, utc_minute = divmod(total_minutes, 60)
    return f"{utc_minute} {utc_hour} * * *"
