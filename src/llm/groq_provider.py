# src/llm/groq_provider.py
"""Groq LLM provider implementation.

Uses the Groq Chat Completion API. Retries are handled via the shared
``execute_with_retry`` utility. No API keys or request payloads are logged.
"""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from src.utils.retry import execute_with_retry

from .provider import LLMProvider, ProviderError


class GroqProvider(LLMProvider):
    """Concrete provider for Groq.

    Reads ``groq_api_key`` from the global ``Settings`` instance.
    """

    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    async def extract(self, prompt: str, max_output_tokens: int | None = None) -> dict:
        api_key = self.settings.groq_api_key
        if not api_key:
            raise ProviderError("Groq API key not configured", provider="groq")

        payload: dict[str, Any] = {
            "model": "llama3-70b-8192",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens

        async def operation() -> aiohttp.ClientResponse:
            async with aiohttp.ClientSession() as session:
                return await session.post(
                    self.API_URL,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                )

        response = await execute_with_retry(
            operation,
            config=self.retry_config,
            url=self.API_URL,
            status_extractor=lambda r: r.status,
        )

        data = await response.json()
        try:
            # Extract content; handle missing keys or malformed JSON
            text = data["choices"][0]["message"]["content"]
            return json.loads(text)
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"Malformed Groq response: {exc}")
