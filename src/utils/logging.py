"""Structured logging setup + run-level observability helpers (Section 33)."""
from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path
from typing import Optional

from src.utils.config import get_settings


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def setup_logging(run_id: Optional[str] = None) -> logging.Logger:
    settings = get_settings()
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("morning_desk")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    file_name = f"run_{run_id}.log" if run_id else "morning_desk.log"
    file_handler = logging.FileHandler(log_dir / file_name)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    logger = logging.getLogger("morning_desk")
    if not logger.handlers:
        return setup_logging()
    return logger
