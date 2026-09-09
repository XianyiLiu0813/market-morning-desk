"""Real EmailProvider implementations: Resend (primary) and SMTP (fallback)."""
from __future__ import annotations

import base64
import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from src.providers.email_base import EmailAttachment, EmailProvider
from src.utils.retry import retry_with_backoff

logger = logging.getLogger("morning_desk")


class ResendEmailProvider(EmailProvider):
    name = "resend"

    def __init__(self, api_key: str):
        self.api_key = api_key

    @retry_with_backoff(max_attempts=3)
    def send(
        self,
        to_addr: str,
        from_addr: str,
        subject: str,
        html_body: str,
        attachments: Optional[List[EmailAttachment]] = None,
    ) -> bool:
        try:
            import resend

            resend.api_key = self.api_key
            payload = {
                "from": from_addr,
                "to": [to_addr],
                "subject": subject,
                "html": html_body,
            }
            if attachments:
                # Resend expects base64-encoded content per attachment.
                # https://resend.com/docs/api-reference/emails/send-email#body-parameters
                payload["attachments"] = [
                    {
                        "filename": att.filename,
                        "content": base64.b64encode(att.content).decode("ascii"),
                    }
                    for att in attachments
                ]
            resend.Emails.send(payload)
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

    def send(
        self,
        to_addr: str,
        from_addr: str,
        subject: str,
        html_body: str,
        attachments: Optional[List[EmailAttachment]] = None,
    ) -> bool:
        try:
            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = to_addr

            body_part = MIMEMultipart("alternative")
            body_part.attach(MIMEText(html_body, "html"))
            msg.attach(body_part)

            for att in attachments or []:
                part = MIMEApplication(att.content, Name=att.filename)
                part["Content-Disposition"] = f'attachment; filename="{att.filename}"'
                msg.attach(part)

            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                if self.use_tls:
                    server.starttls()
                if self.username:
                    server.login(self.username, self.password)
                server.sendmail(from_addr, [to_addr], msg.as_string())
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("SMTP email send failed: %s", exc)
            return False
