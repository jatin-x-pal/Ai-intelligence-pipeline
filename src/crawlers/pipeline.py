"""Generic source crawl pipeline.

Coordinates source configuration, crawler selection (HTTP vs. Playwright browser),
URL deduplication, deterministic HTML cleaning, metadata extraction, and
24-hour freshness validation for news and job postings.
"""

from __future__ import annotations

import asyncio
import types
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Self

from src.crawlers.browser import BrowserCrawler
from src.crawlers.http import HttpCrawler

if TYPE_CHECKING:
    from src.crawlers.base import BaseCrawler, CrawlResult
from src.crawlers.sources import (
    CrawlMethod,
    SourceCategory,
    SourceConfig,
    SourceRegistry,
    load_sources,
)
from src.extraction.date_parser import is_fresh, parse_publication_date
from src.extraction.html_cleaner import CleanedDocument, clean_html
from src.extraction.metadata import ExtractedMetadata, extract_metadata
from src.storage.dedup import BaseDeduplicator, InMemoryDeduplicator
from src.utils.logging import get_logger
from src.utils.urls import normalize_url

logger = get_logger(__name__)


@dataclass(frozen=True)
class CrawledDocument:
    """Structured result of crawling and deterministic extraction for a document."""

    source_name: str
    source_category: SourceCategory
    url: str
    normalized_url: str
    crawl_method: CrawlMethod
    collected_at: datetime
    status_code: int
    is_success: bool
    cleaned_content: CleanedDocument | None = None
    metadata: ExtractedMetadata | None = None
    publication_date: datetime | None = None
    is_fresh: bool | None = None
    is_duplicate: bool = False
    error: str | None = None


class SourceCrawlPipeline:
    """Unified pipeline for crawling configured sources and extracting content."""

    def __init__(
        self,
        *,
        registry: SourceRegistry | None = None,
        deduplicator: BaseDeduplicator | None = None,
        http_crawler: HttpCrawler | None = None,
        browser_crawler: BrowserCrawler | None = None,
    ) -> None:
        """Initialize crawl pipeline.

        Args:
            registry: SourceRegistry instance or None (loads default config/sources.yaml).
            deduplicator: BaseDeduplicator engine or None (defaults to InMemoryDeduplicator).
            http_crawler: Optional pre-configured HttpCrawler instance.
            browser_crawler: Optional pre-configured BrowserCrawler instance.
        """
        self.registry = registry or load_sources()
        self.deduplicator = deduplicator or InMemoryDeduplicator()
        self._http_crawler = http_crawler
        self._browser_crawler = browser_crawler
        self._owns_http = http_crawler is None
        self._owns_browser = browser_crawler is None

        # Per-source concurrency and rate-limiting state
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._last_request_time: dict[str, float] = {}
        self._rate_locks: dict[str, asyncio.Lock] = {}

    def get_http_crawler(self) -> HttpCrawler:
        """Return shared HttpCrawler, instantiating it if necessary."""
        if self._http_crawler is None:
            self._http_crawler = HttpCrawler()
        return self._http_crawler

    def get_browser_crawler(self) -> BrowserCrawler:
        """Return shared BrowserCrawler, instantiating it if necessary."""
        if self._browser_crawler is None:
            self._browser_crawler = BrowserCrawler()
        return self._browser_crawler

    def get_crawler_for_source(self, source: SourceConfig) -> BaseCrawler:
        """Select crawler based on configured crawl_method."""
        if source.crawl_method == CrawlMethod.BROWSER:
            return self.get_browser_crawler()
        return self.get_http_crawler()

    async def _enforce_rate_limit(self, source: SourceConfig) -> None:
        """Enforce per-source request spacing if rate_limit_per_second is configured."""
        if not source.rate_limit_per_second or source.rate_limit_per_second <= 0:
            return

        min_interval = 1.0 / source.rate_limit_per_second
        lock = self._rate_locks.setdefault(source.name, asyncio.Lock())
        async with lock:
            # Use UTC datetime timestamp for rate limiting consistency with tests
            now_ts = datetime.now(UTC).timestamp()
            last_ts = self._last_request_time.get(source.name, 0.0)
            elapsed = now_ts - last_ts
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            self._last_request_time[source.name] = datetime.now(UTC).timestamp()

    async def crawl_source(
        self,
        source_or_name: SourceConfig | str,
        *,
        url: str | None = None,
    ) -> CrawledDocument:
        """Crawl a source URL, perform deduplication, and extract structured document.

        Args:
            source_or_name: SourceConfig object or registered source name.
            url: Optional override URL to crawl (defaults to source.base_url).

        Returns:
            CrawledDocument containing provenance, status, cleaned text, metadata,
            publication date, and freshness evaluation.
        """
        if isinstance(source_or_name, str):
            found = self.registry.get_source(source_or_name)
            if found is None:
                raise ValueError(f"Source '{source_or_name}' not found in registry")
            source = found
        else:
            source = source_or_name

        target_url = url or source.base_url
        collected_at = datetime.now(UTC)

        # 1. Verify source is enabled
        if not source.enabled:
            return CrawledDocument(
                source_name=source.name,
                source_category=source.category,
                url=target_url,
                normalized_url="",
                crawl_method=source.crawl_method,
                collected_at=collected_at,
                status_code=0,
                is_success=False,
                error="Source is disabled in configuration",
            )

        # 2. Normalize target URL
        try:
            canonical_url = normalize_url(target_url)
        except Exception as exc:  # noqa: BLE001
            return CrawledDocument(
                source_name=source.name,
                source_category=source.category,
                url=target_url,
                normalized_url="",
                crawl_method=source.crawl_method,
                collected_at=collected_at,
                status_code=0,
                is_success=False,
                error=f"Invalid URL: {exc}",
            )
        # Enforce rate limiting before deduplication to ensure consistent spacing even for duplicate URLs
        await self._enforce_rate_limit(source)

        # 3. Deduplication check prior to network crawl
        if await self.deduplicator.is_seen(canonical_url):
            return CrawledDocument(
                source_name=source.name,
                source_category=source.category,
                url=target_url,
                normalized_url=canonical_url,
                crawl_method=source.crawl_method,
                collected_at=collected_at,
                status_code=0,
                is_success=False,
                is_duplicate=True,
                error=f"Duplicate URL: {canonical_url} has already been processed",
            )

        # 4. Resolve per-source concurrency semaphore
        semaphore: asyncio.Semaphore | None = None
        if source.max_concurrency and source.max_concurrency > 0:
            semaphore = self._semaphores.setdefault(
                source.name, asyncio.Semaphore(source.max_concurrency)
            )

        async def _execute_fetch_and_extract() -> CrawledDocument:
            await self._enforce_rate_limit(source)
            crawler = self.get_crawler_for_source(source)

            crawl_kwargs: dict[str, Any] = {}
            if source.timeout_seconds:
                crawl_kwargs["timeout"] = source.timeout_seconds
            if source.headers:
                crawl_kwargs["headers"] = source.headers

            fetch_time = datetime.now(UTC)
            try:
                crawl_result: CrawlResult = await crawler.fetch(target_url, **crawl_kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.warning("pipeline_crawl_failed", source=source.name, url=target_url, error=str(exc))
                return CrawledDocument(
                    source_name=source.name,
                    source_category=source.category,
                    url=target_url,
                    normalized_url=canonical_url,
                    crawl_method=source.crawl_method,
                    collected_at=fetch_time,
                    status_code=0,
                    is_success=False,
                    error=f"Crawler error: {type(exc).__name__}: {exc}",
                )

            if not crawl_result.is_success or crawl_result.error:
                return CrawledDocument(
                    source_name=source.name,
                    source_category=source.category,
                    url=target_url,
                    normalized_url=canonical_url,
                    crawl_method=source.crawl_method,
                    collected_at=fetch_time,
                    status_code=crawl_result.status,
                    is_success=False,
                    error=crawl_result.error or f"HTTP {crawl_result.status}",
                )

            # 5. Mark URL as seen in deduplicator after successful crawl
            await self.deduplicator.mark_seen(canonical_url)

            # 6. Deterministic HTML cleaning and metadata extraction
            try:
                cleaned = clean_html(crawl_result.body, source_url=target_url)
                metadata = extract_metadata(crawl_result.body, source_url=target_url)
                pub_date = parse_publication_date(crawl_result.body, reference=fetch_time)

                # Freshness verification only applies to news and job categories
                freshness: bool | None = None
                if source.category in (SourceCategory.NEWS, SourceCategory.JOB):
                    freshness = is_fresh(pub_date, reference=fetch_time)

                return CrawledDocument(
                    source_name=source.name,
                    source_category=source.category,
                    url=target_url,
                    normalized_url=canonical_url,
                    crawl_method=source.crawl_method,
                    collected_at=fetch_time,
                    status_code=crawl_result.status,
                    is_success=True,
                    cleaned_content=cleaned,
                    metadata=metadata,
                    publication_date=pub_date,
                    is_fresh=freshness,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("pipeline_extraction_failed", source=source.name, url=target_url, error=str(exc))
                return CrawledDocument(
                    source_name=source.name,
                    source_category=source.category,
                    url=target_url,
                    normalized_url=canonical_url,
                    crawl_method=source.crawl_method,
                    collected_at=fetch_time,
                    status_code=crawl_result.status,
                    is_success=False,
                    error=f"Extraction error: {type(exc).__name__}: {exc}",
                )

        if semaphore is not None:
            async with semaphore:
                return await _execute_fetch_and_extract()
        return await _execute_fetch_and_extract()

    async def close(self) -> None:
        """Close underlying crawler resources."""
        if self._http_crawler is not None:
            await self._http_crawler.close()
        if self._browser_crawler is not None:
            await self._browser_crawler.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None) -> None:
        await self.close()
