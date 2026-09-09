"""Scheduling helpers (Section 32).

Two supported mechanisms:
1. Local cron / systemd timer calling `python main.py morning` directly
   (recommended for a personal machine/server always on before 07:45 SGT).
2. GitHub Actions workflow_dispatch + cron trigger (see
   .github/workflows/morning.yml) - remember GitHub Actions cron is UTC,
   so the trigger time must be converted from Asia/Singapore.
3. `run_blocking_scheduler()` below: a simple in-process daily scheduler
   for cases where cron/GH Actions isn't available (e.g. a long-running
   container). Not required for MOCK_MODE/testing.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Callable

from src.utils.time import SGT, now_sgt

logger = logging.getLogger("morning_desk")


def seconds_until_next(hour: int, minute: int) -> float:
    now = now_sgt()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_blocking_scheduler(hour: int, minute: int, job: Callable[[], None]) -> None:
    """Blocking loop: sleeps until HH:MM Asia/Singapore each day, then runs
    `job()`. Intended for a long-running process/container; for a personal
    machine, a real cron entry or launchd/systemd timer is simpler and more
    robust (survives process restarts) - see README for the crontab
    example."""
    logger.info("Blocking scheduler started; target run time %02d:%02d Asia/Singapore", hour, minute)
    while True:
        wait_s = seconds_until_next(hour, minute)
        logger.info("Sleeping %.0f seconds until next scheduled run", wait_s)
        time.sleep(wait_s)
        try:
            job()
        except Exception as exc:  # noqa: BLE001
            logger.error("Scheduled job raised an exception: %s", exc)
        # Sleep past the trigger minute so we don't double-fire within the
        # same minute due to timing jitter.
        time.sleep(65)
