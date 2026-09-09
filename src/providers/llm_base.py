"""LLMProvider abstract interface (Section 25).

Every LLM task in src/analysis/* goes through generate_json(), which must
return a raw JSON string. The caller is responsible for schema validation
(src/models/schemas.py) - the LLM layer itself does not know about Pydantic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> str:
        """Return a raw JSON string (no markdown fences). Implementations
        should ask the underlying model for JSON-only output and strip any
        wrapping code fences before returning."""
        raise NotImplementedError

    def last_usage(self) -> Optional[dict]:
        """Optional: return {'input_tokens':..,'output_tokens':..} for the
        most recent call, if the provider tracks it."""
        return None
