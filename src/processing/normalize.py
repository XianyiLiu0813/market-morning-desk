"""Normalization utilities for raw article/text data (Section 9 step 1).

Keeps text handling centralized and defensive: all external text is
treated as untrusted DATA (Section 45) - normalization here strips control
characters and collapses whitespace, it never interprets the text as
instructions.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


_WS_RE = re.compile(r"\s+")


def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    # Strip non-printable/control characters (defends against odd injected
    # unicode formatting tricks in scraped/RSS content).
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")
    text = _WS_RE.sub(" ", text).strip()
    return text


def normalize_title(title: str) -> str:
    """Lowercased, punctuation-stripped title used for similarity matching."""
    t = clean_text(title).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


def truncate(text: str, max_chars: int = 600) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rsplit(" ", 1)[0] + "…"
