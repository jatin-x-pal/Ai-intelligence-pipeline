"""Tests for the generic source crawling pipeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.crawlers.base import CrawlResult
from src.crawlers.browser import BrowserCrawler
from src.crawlers.http import HttpCrawler
from src.crawlers.pipeline import CrawledDocument, SourceCrawlPipeline
from src.crawlers.sources import (
    CrawlMethod,
    SourceCategory,
    SourceConfig,
    SourceRegistry,
)
from src.storage.dedup import InMemoryDeduplicator


@pytest.fixture
def sample_registry() -> SourceRegistry:
    """Create test registry with sample sources across different categories."""
    sources = [
        SourceConfig(
            name="AI News Daily",
            base_url="https://news.example.com/ai",
            category=SourceCategory.NEWS,
            crawl_method=CrawlMethod.HTTP,
            enabled=True,
            rate_limit_per_second=10.0,
            max_concurrency=2,
        ),
        SourceConfig(
            name="AI Job Board",
            base_url="https://jobs.example.com",
            category=SourceCategory.JOB,
            crawl_method=CrawlMethod.BROWSER,
            enabled=True,
        ),
        SourceConfig(
            name="Startup Directory",
            base_url="https://startups.example.com/directory",
            category=SourceCategory.STARTUP,
            crawl_method=CrawlMethod.HTTP,
            enabled=True,
        ),
        SourceConfig(
            name="Disabled Source",
            base_url="https://disabled.example.com",
            category=SourceCategory.NEWS,
            crawl_method=CrawlMethod.HTTP,
            enabled=False,
        ),
    ]
    return SourceRegistry(sources=sources)


@pytest.fixture
def mock_http_crawler() -> HttpCrawler:
    """Create mock HTTP crawler."""
    crawler = AsyncMock(spec=HttpCrawler)
    crawler.close = AsyncMock()
    return crawler


@pytest.fixture
def mock_browser_crawler() -> BrowserCrawler:
    """Create mock Browser crawler."""
    crawler = AsyncMock(spec=BrowserCrawler)
    crawler.close = AsyncMock()
    return crawler


class TestSourceCrawlPipeline:
    """Tests for SourceCrawlPipeline functionality."""

    @pytest.mark.asyncio
    async def test_crawler_selection_by_method(
        self,
        sample_registry: SourceRegistry,
        mock_http_crawler: HttpCrawler,
        mock_browser_crawler: BrowserCrawler,
    ) -> None:
        mock_http_crawler.fetch = AsyncMock(
            return_value=CrawlResult(
                url="https://news.example.com/ai",
                status=200,
                body="<html><body><h1>AI News</h1><p>Content</p></body></html>",
            )
        )
        mock_browser_crawler.fetch = AsyncMock(
            return_value=CrawlResult(
                url="https://jobs.example.com",
                status=200,
                body="<html><body><h1>Jobs</h1><p>Content</p></body></html>",
            )
        )

        pipeline = SourceCrawlPipeline(
            registry=sample_registry,
            http_crawler=mock_http_crawler,
            browser_crawler=mock_browser_crawler,
        )

        # 1. HTTP source triggers http_crawler
        doc_http = await pipeline.crawl_source("AI News Daily")
        assert doc_http.is_success is True
        mock_http_crawler.fetch.assert_awaited_once()
        mock_browser_crawler.fetch.assert_not_awaited()

        # 2. Browser source triggers browser_crawler
        doc_browser = await pipeline.crawl_source("AI Job Board")
        assert doc_browser.is_success is True
        mock_browser_crawler.fetch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_successful_crawl_and_extraction(
        self,
        sample_registry: SourceRegistry,
        mock_http_crawler: HttpCrawler,
    ) -> None:
        recent_date = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        html = f"""
        <html>
            <head>
                <title>Revolution in AI Agents</title>
                <meta property="og:description" content="A breakthrough in agent architectures." />
                <link rel="canonical" href="https://news.example.com/ai/article-1" />
                <script type="application/ld+json">
                {{"@context": "https://schema.org", "@type": "NewsArticle", "datePublished": "{recent_date}"}}
                </script>
            </head>
            <body>
                <header>Navigation</header>
                <main>
                    <h1>Revolution in AI Agents</h1>
                    <p>Substantive article paragraphs describing autonomous agent progress.</p>
                </main>
                <footer>Footer text</footer>
            </body>
        </html>
        """
        mock_http_crawler.fetch = AsyncMock(
            return_value=CrawlResult(
                url="https://news.example.com/ai/article-1",
                status=200,
                body=html,
            )
        )

        pipeline = SourceCrawlPipeline(
            registry=sample_registry,
            http_crawler=mock_http_crawler,
        )

        doc = await pipeline.crawl_source("AI News Daily", url="https://news.example.com/ai/article-1?utm_source=twitter")

        assert isinstance(doc, CrawledDocument)
        assert doc.is_success is True
        assert doc.source_name == "AI News Daily"
        assert doc.source_category == SourceCategory.NEWS
        assert doc.status_code == 200
        assert doc.normalized_url == "https://news.example.com/ai/article-1"
        assert doc.cleaned_content is not None
        assert "Revolution in AI Agents" in doc.cleaned_content.clean_text
        assert "Navigation" not in doc.cleaned_content.clean_text
        assert doc.metadata is not None
        assert doc.metadata.title == "Revolution in AI Agents"
        assert doc.metadata.canonical_url == "https://news.example.com/ai/article-1"
        assert doc.publication_date is not None
        assert doc.is_fresh is True

    @pytest.mark.asyncio
    async def test_deduplication_prevents_re_crawl(
        self,
        sample_registry: SourceRegistry,
        mock_http_crawler: HttpCrawler,
    ) -> None:
        mock_http_crawler.fetch = AsyncMock(
            return_value=CrawlResult(
                url="https://startups.example.com/directory",
                status=200,
                body="<html><body><h1>Startups</h1><p>Directory</p></body></html>",
            )
        )
        dedup = InMemoryDeduplicator()
        pipeline = SourceCrawlPipeline(
            registry=sample_registry,
            deduplicator=dedup,
            http_crawler=mock_http_crawler,
        )

        # First crawl succeeds
        doc1 = await pipeline.crawl_source("Startup Directory", url="https://startups.example.com/directory?utm_campaign=seed")
        assert doc1.is_success is True
        assert doc1.is_duplicate is False
        assert mock_http_crawler.fetch.await_count == 1

        # Second crawl of equivalent URL is detected as duplicate without invoking crawler
        doc2 = await pipeline.crawl_source("Startup Directory", url="HTTPS://STARTUPS.EXAMPLE.COM/directory?utm_medium=cpc#top")
        assert doc2.is_success is False
        assert doc2.is_duplicate is True
        assert "Duplicate URL" in str(doc2.error)
        assert mock_http_crawler.fetch.await_count == 1  # No second network call

    @pytest.mark.asyncio
    async def test_freshness_logic_by_category(
        self,
        sample_registry: SourceRegistry,
        mock_http_crawler: HttpCrawler,
    ) -> None:
        stale_date = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        html_stale = f"""
        <html>
            <head>
                <script type="application/ld+json">
                {{"@context": "https://schema.org", "datePublished": "{stale_date}"}}
                </script>
            </head>
            <body><p>Article text</p></body>
        </html>
        """
        mock_http_crawler.fetch = AsyncMock(
            return_value=CrawlResult(
                url="https://news.example.com/ai/stale",
                status=200,
                body=html_stale,
            )
        )

        pipeline = SourceCrawlPipeline(
            registry=sample_registry,
            http_crawler=mock_http_crawler,
        )

        # 1. News source with stale date evaluates to is_fresh=False
        doc_news = await pipeline.crawl_source("AI News Daily", url="https://news.example.com/ai/stale")
        assert doc_news.is_fresh is False

        # 2. Startup source evaluates to is_fresh=None (freshness not enforced)
        mock_http_crawler.fetch = AsyncMock(
            return_value=CrawlResult(
                url="https://startups.example.com/directory",
                status=200,
                body=html_stale,
            )
        )
        doc_startup = await pipeline.crawl_source("Startup Directory")
        assert doc_startup.is_fresh is None

    @pytest.mark.asyncio
    async def test_disabled_source_rejected(
        self,
        sample_registry: SourceRegistry,
        mock_http_crawler: HttpCrawler,
    ) -> None:
        pipeline = SourceCrawlPipeline(
            registry=sample_registry,
            http_crawler=mock_http_crawler,
        )
        doc = await pipeline.crawl_source("Disabled Source")
        assert doc.is_success is False
        assert "Source is disabled" in str(doc.error)
        mock_http_crawler.fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_http_error_response_handled_gracefully(
        self,
        sample_registry: SourceRegistry,
        mock_http_crawler: HttpCrawler,
    ) -> None:
        mock_http_crawler.fetch = AsyncMock(
            return_value=CrawlResult(
                url="https://news.example.com/ai/missing",
                status=404,
                body="",
                error="Not Found",
            )
        )
        pipeline = SourceCrawlPipeline(
            registry=sample_registry,
            http_crawler=mock_http_crawler,
        )
        doc = await pipeline.crawl_source("AI News Daily", url="https://news.example.com/ai/missing")
        assert doc.is_success is False
        assert doc.status_code == 404
        assert "Not Found" in str(doc.error)

    @pytest.mark.asyncio
    async def test_network_exception_handled_gracefully(
        self,
        sample_registry: SourceRegistry,
        mock_http_crawler: HttpCrawler,
    ) -> None:
        mock_http_crawler.fetch = AsyncMock(side_effect=TimeoutError("Connection timed out"))
        pipeline = SourceCrawlPipeline(
            registry=sample_registry,
            http_crawler=mock_http_crawler,
        )
        doc = await pipeline.crawl_source("AI News Daily")
        assert doc.is_success is False
        assert doc.status_code == 0
        assert "TimeoutError" in str(doc.error)

    @pytest.mark.asyncio
    async def test_invalid_source_name_raises(
        self,
        sample_registry: SourceRegistry,
    ) -> None:
        pipeline = SourceCrawlPipeline(registry=sample_registry)
        with pytest.raises(ValueError, match="Source 'Nonexistent' not found"):
            await pipeline.crawl_source("Nonexistent")

    @pytest.mark.asyncio
    async def test_pipeline_close_and_context_manager(
        self,
        sample_registry: SourceRegistry,
        mock_http_crawler: HttpCrawler,
        mock_browser_crawler: BrowserCrawler,
    ) -> None:
        async with SourceCrawlPipeline(
            registry=sample_registry,
            http_crawler=mock_http_crawler,
            browser_crawler=mock_browser_crawler,
        ) as pipeline:
            assert pipeline is not None
        # Both crawlers should be closed cleanly
        mock_http_crawler.close.assert_awaited_once()
        mock_browser_crawler.close.assert_awaited_once()
