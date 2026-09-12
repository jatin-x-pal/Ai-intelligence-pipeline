# src/llm/gemini_provider.py
"""Gemini LLM provider implementation.

Uses the Gemini Generative Language API. The provider respects the retry
configuration from ``src.utils.retry`` and raises ``ProviderError`` on failures.
No API keys or request payloads are logged.
"""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from src.utils.retry import execute_with_retry

from .provider import LLMProvider, ProviderError


class GeminiProvider(LLMProvider):
    """Concrete Gemini provider.

    Reads the ``GEMINI_API_KEY`` from the global ``Settings`` instance.
    """

    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"

    async def extract(self, prompt: str, max_output_tokens: int | None = None) -> dict[str, Any]:
        api_key = self.settings.gemini_api_key
        if not api_key:
            raise ProviderError("Gemini API key not configured", provider="gemini")

        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}]
        }
        if max_output_tokens is not None:
            payload["generationConfig"] = {"maxOutputTokens": max_output_tokens}

        async def operation() -> aiohttp.ClientResponse:
            async with aiohttp.ClientSession() as session:
                return await session.post(
                    self.API_URL,
                    params={"key": api_key},
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                )

        # Execute with retry; we only need the status code for retry decisions.
        response = await execute_with_retry(
            operation,
            config=self.retry_config,
            url=self.API_URL,
            status_extractor=lambda resp: resp.status,
        )

        data = await response.json()
        # Expected path to generated text.
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            # Assume the model returns JSON string.
            return json.loads(text)
        except (json.JSONDecodeError, KeyError) as exc:
            raise ValueError(f"Malformed Gemini response: {exc}")
