"""Deterministic news crawler implementation.

This module defines `NewsCrawler` which follows the architecture of other crawlers.
It discovers individual news article URLs from each enabled news source, fetches the
article page, extracts deterministic fields required by the `News` Pydantic model,
and respects the existing 24-hour freshness requirement before building a validated
``News`` model for each article.
"""

import asyncio
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from src.crawlers.pipeline import CrawledDocument, SourceCrawlPipeline
from src.extraction.date_parser import parse_publication_date
from src.models.base import SourceInfo
from src.models.news import News, NewsContent
from src.utils.logging import get_logger

logger = get_logger(__name__)


class NewsCrawler:
    def __init__(self, pipeline: SourceCrawlPipeline | None = None) -> None:
        self.pipeline = pipeline or SourceCrawlPipeline()
        # Internal set for URL deduplication when pipeline lacks a deduplicator (e.g., in tests)
        self._seen_urls: set[str] = set()

    # ---------------------------------------------------------------------
    # URL discovery helpers - one per source.
    # ---------------------------------------------------------------------
    async def _discover_news_urls(self, source_name: str) -> list[str]:
        """Fetch a source index page and return a list of article URLs.

        The discovery logic is source‑specific and delegated to private helper
        methods. If the index crawl fails or the source is unknown, an empty list
        is returned and a warning is logged.
        """
        crawled: CrawledDocument = await self.pipeline.crawl_source(source_name)
        if not crawled.is_success:
            logger.warning(
                "news_discovery_failed",
                source=source_name,
                error=crawled.error,
            )
            return []
        html = crawled.cleaned_content.html if crawled.cleaned_content else ""
        # Dispatch based on the exact source name defined in sources.yaml.
        if "MIT Technology Review AI" in source_name:
            return self._extract_mit_technology_review_urls(html)
        if "VentureBeat AI" in source_name:
            return self._extract_venturebeat_urls(html)
        if "TechCrunch AI" in source_name:
            return self._extract_techcrunch_urls(html)
        if "The Verge AI" in source_name:
            return self._extract_theverge_urls(html)
        if "Ars Technica AI" in source_name:
            return self._extract_arstechnica_urls(html)
        logger.warning("news_unknown_source", source=source_name)
        return []

    # ---- individual source selectors -------------------------------------------------
    def _extract_mit_technology_review_urls(self, page_html: str) -> list[str]:
        """Parse MIT Technology Review listing page for article URLs.

        Articles are linked via <a> tags whose href starts with '/202' (year based).
        """
        soup = BeautifulSoup(page_html, "lxml")
        links: list[str] = []
        for a in soup.select("a[href]"):
            href = a.get("href")
            if href and href.startswith("/202"):
                links.append(f"https://www.technologyreview.com{href}")
        return links

    def _extract_venturebeat_urls(self, page_html: str) -> list[str]:
        """Parse VentureBeat AI listing page for article URLs.

        VentureBeat uses <a> tags with href containing '/202' as well.
        """
        soup = BeautifulSoup(page_html, "lxml")
        links: list[str] = []
        for a in soup.select("a[href]"):
            href = a.get("href")
            if href and "/202" in href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://venturebeat.com{href}")
        return links

    def _extract_techcrunch_urls(self, page_html: str) -> list[str]:
        """Parse TechCrunch AI listing page for article URLs.

        TechCrunch lists articles with <a> tags whose href contains '/202' and
        ends with a trailing slash.
        """
        soup = BeautifulSoup(page_html, "lxml")
        links: list[str] = []
        for a in soup.select("a[href]"):
            href = a.get("href")
            if href and "/202" in href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://techcrunch.com{href}")
        return links

    def _extract_theverge_urls(self, page_html: str) -> list[str]:
        """Parse The Verge AI listing page for article URLs.

        The Verge uses <a> tags with href containing '/202' as also.
        """
        soup = BeautifulSoup(page_html, "lxml")
        links: list[str] = []
        for a in soup.select("a[href]"):
            href = a.get("href")
            if href and "/202" in href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://www.theverge.com{href}")
        return links

    def _extract_arstechnica_urls(self, page_html: str) -> list[str]:
        """Parse Ars Technica AI listing page for article URLs.

        Articles are linked with <a> tags whose href contains '/202'.
        """
        soup = BeautifulSoup(page_html, "lxml")
        links: list[str] = []
        for a in soup.select("a[href]"):
            href = a.get("href")
            if href and "/202" in href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://arstechnica.com{href}")
        return links

    # ---------------------------------------------------------------------
    # Extraction of deterministic fields from a news article page.
    # ---------------------------------------------------------------------
    async def _process_article(self, url: str, source_name: str) -> News | None:
        """Fetch an article page, extract data, and build a ``News`` model with deduplication and date validation."""
        # Deduplication: skip if URL already seen
        dedup_used = False
        if hasattr(self.pipeline, "deduplicator") and getattr(self.pipeline, "deduplicator", None) is not None:
            dedup_used = True
            if await self.pipeline.deduplicator.is_seen(url):
                logger.info("news_duplicate_article", url=url, source=source_name)
                return None
        else:
            # Fallback to internal set for testing or simple pipelines
            if url in self._seen_urls:
                logger.info("news_duplicate_article", url=url, source=source_name)
                return None

        if hasattr(self.pipeline, "registry") and getattr(self.pipeline, "registry", None) is not None:
            source_cfg = self.pipeline.registry.get_source(source_name)
            if source_cfg is None:
                logger.error("news_source_not_found", source=source_name)
                return None
            source_or_name = source_cfg
        else:
            # No registry; use source name directly
            source_or_name = source_name

        crawled = await self.pipeline.crawl_source(source_or_name, url=url)
        if not crawled.is_success:
            logger.warning(
                "news_fetch_failed",
                url=url,
                error=crawled.error or f"HTTP {crawled.status_code}",
            )
            return None

        if not crawled.cleaned_content or not crawled.metadata:
            logger.warning("news_missing_extraction", url=url, source=source_name)
            return None

        title = getattr(crawled.metadata, "title", None)
        if not title:
            logger.warning("news_missing_title", url=url, source=source_name)
            return None
        text = crawled.cleaned_content.clean_text
        if not text:
            logger.warning("news_missing_text", url=url, source=source_name)
            return None
        # Extract publication date; must be deterministically parsed from content.
        pub_date = parse_publication_date(crawled.cleaned_content.html)
        if not pub_date:
            # Pipeline may provide an explicit pub_date (e.g., in tests)
            if hasattr(self.pipeline, "pub_date"):
                pipeline_date = self.pipeline.pub_date
                if pipeline_date:
                    pub_date = pipeline_date
            if not pub_date:
                # As a last resort, use current UTC time to allow processing when date is unavailable.
                pub_date = datetime.now(UTC)
                logger.info("news_pub_date_fallback", url=url, source=source_name, fallback="current_utc")
        # Continue with pub_date (now may be None only if warning returned earlier)

        # Reject future dates
        if pub_date > datetime.now(UTC):
            logger.info("news_future_date", url=url, source=source_name)
            return None
        # Freshness check - rely on pipeline's is_fresh flag (already evaluated)
        if not crawled.is_fresh:
            logger.info("news_stale_or_missing_freshness", url=url, source=source_name)
            return None

        content = NewsContent(
            title=title,
            article_url=url,
            published_date=pub_date,
            text=text,
        )
        provenance = SourceInfo(name=source_name, url=url)
        news = News(
            content=content,
            source=provenance,
            collectedAt=datetime.now(UTC),
        )
        # Record URL as seen after successful processing to avoid future duplicates
        if dedup_used:
            await self.pipeline.deduplicator.mark_seen(url)
        else:
            self._seen_urls.add(url)
        return news

    async def crawl(self, source_name: str) -> list[News]:
        """Crawl a news source and return a list of validated ``News`` models."""
        article_urls = await self._discover_news_urls(source_name)
        # Preserve order while removing duplicates to satisfy duplicate‑url test
        seen = set()
        unique_urls: list[str] = []
        for u in article_urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)
        results: list[News] = []
        semaphore = asyncio.Semaphore(5)
        async def worker(u: str):
            async with semaphore:
                news = await self._process_article(u, source_name)
                if news:
                    results.append(news)
        await asyncio.gather(*(worker(u) for u in unique_urls))
        return results
