"""Email dispatch wrapper (Section 31)."""
from __future__ import annotations

import logging
import os
from typing import Optional

from src.providers.email_base import EmailAttachment, EmailProvider
from src.utils.config import Settings

logger = logging.getLogger("morning_desk")

_SHORT_BODY_TEMPLATE = """
<div lang="zh-CN" style="font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Segoe UI',Helvetica,Arial,sans-serif;
            max-width:480px;margin:0 auto;padding:24px;color:#1a1d23;">
  <div style="font-size:12px;letter-spacing:1.2px;text-transform:uppercase;color:#6b7280;margin-bottom:4px;">
    AI Market Morning Desk
  </div>
  <h2 style="margin:0 0 10px 0;">{run_date} 的报告已附上</h2>
  <p style="font-size:13.5px;line-height:1.6;color:#33383f;">
    今日的市场情报与交易导师报告已作为 PDF 附件发送{page_hint}。一句话摘要：{summary}
  </p>
  <p style="font-size:11px;line-height:1.6;color:#8a8f98;margin-top:20px;">
    本报告是一个 AI 辅助的市场研究与学习工具，不构成投资建议（not financial advice）。
    信息可能不完整或存在误差，交易前请务必通过一手信息源核实关键信息。
  </p>
</div>
"""


def build_short_notification_body(run_date, summary: Optional[str], page_count: Optional[int] = None) -> str:
    """Short email body used when the full report is delivered as a PDF
    attachment instead of a long HTML email (avoids sending the same
    content twice)."""
    return _SHORT_BODY_TEMPLATE.format(
        run_date=run_date,
        summary=summary or "详见附件。",
        page_hint=f"（{page_count} 页）" if page_count else "",
    )


def send_morning_email(
    provider: EmailProvider,
    settings: Settings,
    run_date,
    html_body: str,
    pdf_bytes: Optional[bytes] = None,
    pdf_filename: Optional[str] = None,
    summary: Optional[str] = None,
) -> bool:
    to_addr = os.environ.get("EMAIL_TO")
    from_addr = os.environ.get("EMAIL_FROM", "morning-desk@example.com")

    if not to_addr:
        logger.warning("EMAIL_TO is not set; skipping email send (report was still generated and saved).")
        return False

    subject = f"{settings.email_subject_prefix} — {run_date}"

    attachments = None
    body = html_body
    if pdf_bytes is not None:
        filename = pdf_filename or f"morning_desk_{run_date}.pdf"
        attachments = [EmailAttachment(filename=filename, content=pdf_bytes, mime_type="application/pdf")]
        page_count = None
        try:
            import io

            from pypdf import PdfReader

            page_count = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
        except Exception:  # noqa: BLE001
            pass  # page count is a nice-to-have in the notification text, not required
        body = build_short_notification_body(run_date, summary, page_count)

    success = provider.send(
        to_addr=to_addr, from_addr=from_addr, subject=subject, html_body=body, attachments=attachments
    )
    if success:
        logger.info(
            "Email sent via '%s' provider to %s%s",
            provider.name,
            to_addr,
            " (with PDF attachment)" if attachments else "",
        )
    else:
        logger.error("Email send via '%s' provider failed", provider.name)
    return success
