"""Real LLMProvider implementations: Anthropic and OpenAI.

Both are asked to return JSON-only output. Anthropic/OpenAI model names are
never hardcoded beyond the configured default - LLM_MODEL env var (or
config/settings.yaml `llm.model`) controls this (Section 25).
"""
from __future__ import annotations

import json
import logging
import re

from src.providers.llm_base import LLMProvider

logger = logging.getLogger("morning_desk")

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


class AnthropicLLMProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key)
        self.model = model
        self._last_usage = None

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        self._last_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return _strip_fences(text)

    def last_usage(self):
        return self._last_usage


class OpenAILLMProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self._last_usage = None

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        # Newer "reasoning" model families (o1/o3/gpt-5-style) reject the
        # legacy `max_tokens` param (must use `max_completion_tokens`) and
        # often reject any non-default `temperature`. Try the modern/full
        # request first, then degrade parameter-by-parameter on the
        # specific 400 errors those models raise, rather than guessing
        # up front which family `self.model` belongs to.
        attempts = [
            {"max_completion_tokens": max_tokens, "temperature": temperature},
            {"max_completion_tokens": max_tokens},
            {"max_tokens": max_tokens},
        ]
        last_exc: Exception = RuntimeError("unreachable")
        for kwargs in attempts:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    response_format={"type": "json_object"},
                    messages=messages,
                    **kwargs,
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                msg = str(exc).lower()
                if "max_tokens" in msg or "max_completion_tokens" in msg or "temperature" in msg:
                    continue  # try the next, more conservative parameter set
                raise
        else:
            raise last_exc

        text = response.choices[0].message.content or "{}"
        usage = getattr(response, "usage", None)
        if usage:
            self._last_usage = {
                "input_tokens": usage.prompt_tokens,
                "output_tokens": usage.completion_tokens,
            }
        return _strip_fences(text)

    def last_usage(self):
        return self._last_usage
