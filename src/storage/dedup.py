"""URL deduplication interface and storage backends.

Defines the abstract contract for pipeline deduplication engines and
provides an in-memory, asyncio-safe implementation ready for distributed
or Redis-backed extension.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from src.utils.urls import compute_dedup_key, is_valid_url


class BaseDeduplicator(ABC):
    """Abstract interface for URL deduplication engines."""

    @abstractmethod
    async def is_seen(self, url: str) -> bool:
        """Check if a URL (or its normalized key) has already been processed.

        Args:
            url: The URL to inspect.

        Returns:
            True if the URL was previously marked as seen, False otherwise.
        """

    @abstractmethod
    async def mark_seen(self, url: str) -> bool:
        """Mark a URL as seen.

        Args:
            url: The URL to mark.

        Returns:
            True if the URL was newly added, False if it was already present.
        """

    @abstractmethod
    async def check_and_set(self, url: str) -> bool:
        """Atomically check whether a URL is duplicate and record it if new.

        Args:
            url: The URL to evaluate.

        Returns:
            True if the URL is newly added (was NOT a duplicate).
            False if the URL was already seen (is a duplicate).
        """

    @abstractmethod
    async def count(self) -> int:
        """Return the number of unique URLs currently recorded."""

    @abstractmethod
    async def clear(self) -> None:
        """Clear all recorded deduplication entries."""


class InMemoryDeduplicator(BaseDeduplicator):
    """In-memory, async-safe deduplication engine.

    Normalizes input URLs to 64-character SHA-256 keys and maintains an in-memory
    set guarded by an asyncio.Lock for concurrent coroutine safety.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._lock = asyncio.Lock()

    async def is_seen(self, url: str) -> bool:
        """Return True if URL has already been recorded."""
        if not is_valid_url(url):
            return False
        key = compute_dedup_key(url)
        async with self._lock:
            return key in self._seen

    async def mark_seen(self, url: str) -> bool:
        """Mark URL as seen.

        Returns:
            True if URL was newly added, False if already seen.

        Raises:
            ValueError: If the URL is invalid.
        """
        key = compute_dedup_key(url)
        async with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            return True

    async def check_and_set(self, url: str) -> bool:
        """Atomically test and record URL.

        Returns:
            True if newly recorded (first time seen), False if duplicate.
        """
        return await self.mark_seen(url)

    async def count(self) -> int:
        """Return the total number of unique keys tracked."""
        async with self._lock:
            return len(self._seen)

    async def clear(self) -> None:
        """Remove all recorded keys."""
        async with self._lock:
            self._seen.clear()
