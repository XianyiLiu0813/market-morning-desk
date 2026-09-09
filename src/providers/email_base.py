"""EmailProvider abstract interface (Section 31)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class EmailAttachment:
    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"


class EmailProvider(ABC):
    name: str = "base"

    @abstractmethod
    def send(
        self,
        to_addr: str,
        from_addr: str,
        subject: str,
        html_body: str,
        attachments: Optional[List[EmailAttachment]] = None,
    ) -> bool:
        """Return True on success. Must not raise on ordinary send failures -
        log and return False so the pipeline can record email_status=failed
        without crashing the whole run. `attachments` is optional (used for
        the PDF-report delivery mode) - implementations that don't support
        attachments should still send the html_body and log a warning
        rather than silently dropping the attachment."""
        raise NotImplementedError
