"""EmailProvider abstract interface (Section 31)."""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmailProvider(ABC):
    name: str = "base"

    @abstractmethod
    def send(self, to_addr: str, from_addr: str, subject: str, html_body: str) -> bool:
        """Return True on success. Must not raise on ordinary send failures -
        log and return False so the pipeline can record email_status=failed
        without crashing the whole run."""
        raise NotImplementedError
