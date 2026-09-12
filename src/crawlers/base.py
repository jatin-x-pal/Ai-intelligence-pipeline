"""Base crawler interfaces and data structures."""

import asyncio
import types
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Self


@dataclass
class CrawlResult:
    """Standardized result returned by all crawlers."""

    url: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    content_type: str = ""
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """True if HTTP status indicates success (2xx)."""
        return 200 <= self.status < 300


class BaseCrawler(ABC):
    """Abstract base class for all async crawlers."""

    def __init__(
        self,
        *,
        max_concurrency: int = 10,
        timeout: float = 30.0,
    ) -> None:
        """Initialize crawler with bounded concurrency and timeout.

        Args:
            max_concurrency: Maximum number of simultaneous operations.
            timeout: Default timeout in seconds for operations.
        """
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if timeout <= 0:
            raise ValueError("timeout must be greater than 0")

        self.max_concurrency = max_concurrency
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @property
    def current_concurrency(self) -> int:
        """Current number of active slots in use."""
        return self.max_concurrency - self._semaphore._value

    @abstractmethod
    async def fetch(self, url: str, **kwargs: Any) -> CrawlResult:
        """Fetch content from the given URL.

        Args:
            url: The target URL to crawl.
            **kwargs: Crawler-specific parameters.

        Returns:
            A CrawlResult containing status, headers, and body.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release all allocated resources (sessions, pools, browsers)."""
        ...

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.close()
