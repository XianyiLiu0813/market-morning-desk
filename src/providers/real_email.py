"""Real EmailProvider implementations: Resend (primary) and SMTP (fallback)."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.providers.email_base import EmailProvider
from src.utils.retry import retry_with_backoff

logger = logging.getLogger("morning_desk")


class ResendEmailProvider(EmailProvider):
    name = "resend"

    def __init__(self, api_key: str):
        self.api_key = api_key

    @retry_with_backoff(max_attempts=3)
    def send(self, to_addr: str, from_addr: str, subject: str, html_body: str) -> bool:
        try:
            import resend

            resend.api_key = self.api_key
            resend.Emails.send(
                {
                    "from": from_addr,
                    "to": [to_addr],
                    "subject": subject,
                    "html": html_body,
                }
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Resend email send failed: %s", exc)
            return False


class SmtpEmailProvider(EmailProvider):
    name = "smtp"

    def __init__(self, host: str, port: int, username: str, password: str, use_tls: bool = True):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def send(self, to_addr: str, from_addr: str, subject: str, html_body: str) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = to_addr
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                if self.use_tls:
                    server.starttls()
                if self.username:
                    server.login(self.username, self.password)
                server.sendmail(from_addr, [to_addr], msg.as_string())
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("SMTP email send failed: %s", exc)
            return False
