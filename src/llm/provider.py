# src/llm/provider.py
"""Abstract base class for LLM providers.

Providers must implement an asynchronous ``extract`` method that receives a prompt
(and optionally a maximum token count) and returns a Python ``dict`` containing the
structured response from the model.

All providers share the same retry logic (via ``src.utils.retry``) and pull API
keys from the application ``Settings`` instance - no keys are logged.
"""

from __future__ import annotations

import abc
from typing import Any

from src.config import get_settings
from src.utils.retry import RetryConfig


class ProviderError(Exception):
    """Base class for provider‑specific errors.

    Args:
        message: Human readable description.
        provider: Optional identifier of the provider.
    """
    def __init__(self, message: str, *, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider


class LLMProvider(abc.ABC):
    """Base class for LLM providers.

    Sub‑classes should be lightweight - they receive the global ``Settings``
    instance at construction time and use it to read the appropriate API key.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.retry_config = RetryConfig()

    @abc.abstractmethod
    async def extract(self, prompt: str, max_output_tokens: int | None = None) -> dict[str, Any]:
        """Send *prompt* to the model and return a parsed JSON dict.

        Implementations must raise ``ValueError`` if the provider returns malformed
        JSON or the response cannot be parsed into a ``dict``.
        """
        raise NotImplementedError
