"""Email dispatch wrapper (Section 31)."""
from __future__ import annotations

import logging
import os

from src.providers.email_base import EmailProvider
from src.utils.config import Settings

logger = logging.getLogger("morning_desk")


def send_morning_email(
    provider: EmailProvider, settings: Settings, run_date, html_body: str
) -> bool:
    to_addr = os.environ.get("EMAIL_TO")
    from_addr = os.environ.get("EMAIL_FROM", "morning-desk@example.com")

    if not to_addr:
        logger.warning("EMAIL_TO is not set; skipping email send (report was still generated and saved).")
        return False

    subject = f"{settings.email_subject_prefix} — {run_date}"
    success = provider.send(to_addr=to_addr, from_addr=from_addr, subject=subject, html_body=html_body)
    if success:
        logger.info("Email sent via '%s' provider to %s", provider.name, to_addr)
    else:
        logger.error("Email send via '%s' provider failed", provider.name)
    return success
