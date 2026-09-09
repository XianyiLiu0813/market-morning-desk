"""Timezone conversion tests (Section 35)."""
from __future__ import annotations

from datetime import datetime, timezone

from src.utils.time import now_sgt, parse_run_date, sgt_to_utc_cron, to_sgt


def test_to_sgt_converts_utc_correctly():
    utc_dt = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)  # 08:00 SGT
    sgt_dt = to_sgt(utc_dt)
    assert sgt_dt.hour == 8


def test_to_sgt_handles_naive_datetime_as_utc():
    naive_dt = datetime(2026, 9, 9, 0, 0)  # treated as UTC -> 08:00 SGT
    sgt_dt = to_sgt(naive_dt)
    assert sgt_dt.hour == 8


def test_parse_run_date_explicit():
    d = parse_run_date("2026-09-09")
    assert d.year == 2026 and d.month == 9 and d.day == 9


def test_parse_run_date_defaults_to_today_sgt():
    d = parse_run_date(None)
    assert d == now_sgt().date()


def test_sgt_to_utc_cron_0745_sgt_is_2345_utc_prev_day():
    # 07:45 Asia/Singapore (UTC+8, no DST) = 23:45 UTC the previous day.
    cron = sgt_to_utc_cron(7, 45)
    assert cron == "45 23 * * *"


def test_sgt_to_utc_cron_handles_wraparound_near_midnight():
    # 03:00 Asia/Singapore = 19:00 UTC previous day.
    cron = sgt_to_utc_cron(3, 0)
    assert cron == "0 19 * * *"
