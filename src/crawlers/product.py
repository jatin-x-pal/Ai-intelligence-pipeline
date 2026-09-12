# mypy: ignore-errors
'''"""Deterministic product crawler implementation.

This module defines `ProductCrawler` which mirrors the architecture of
`StartupCrawler` but extracts only the fields required by the `Product`
Pydantic model (`startupName` and `pricingModel`).
"""'''

import asyncio
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from src.crawlers.pipeline import SourceCrawlPipeline
from src.models.product import PricingModel, Product, ProductContent, SourceInfo
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ProductCrawler:
    """Crawler for the product category.

    It uses the generic ``SourceCrawlPipeline`` to fetch the index pages for
    each enabled product source, discovers individual product URLs, then fetches
    each product page and builds a validated ``Product`` model.
    """

    def __init__(self, pipeline: SourceCrawlPipeline | None = None) -> None:
        self.pipeline = pipeline or SourceCrawlPipeline()

    async def _discover_product_urls(self, source_name: str) -> list[str]:
        """Fetch a source index page and return a list of product URLs.

        The discovery logic is source-specific and delegated to helper methods.
        """
        crawled = await self.pipeline.crawl_source(source_name)
        if not crawled.is_success:
            logger.warning(
                "product_discovery_failed",
                source=source_name,
                error=crawled.error,
            )
            return []
        html = crawled.cleaned_content.html if crawled.cleaned_content else ""
        if "Product Hunt AI" in source_name:
            return self._extract_product_hunt_urls(html)
        if "Futurepedia" in source_name:
            return self._extract_futurepedia_urls(html)
        if "Theres An AI For That" in source_name:
            return self._extract_there_an_ai_for_that_urls(html)
        logger.warning("product_unknown_source", source=source_name)
        return []

    def _extract_product_hunt_urls(self, page_html: str) -> list[str]:
        """Parse the Product Hunt listing page for individual product URLs.

        Product Hunt uses ``a[data-test='post-link']`` for each product card.
        """
        soup = BeautifulSoup(page_html, "lxml")
        links: list[str] = []
        for a in soup.select("a[data-test='post-link']"):
            href = a.get("href")
            if href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://www.producthunt.com{href}")
        return links

    def _extract_futurepedia_urls(self, page_html: str) -> list[str]:
        """Parse Futurepedia for product detail URLs.

        Futurepedia lists cards with ``a.card`` where ``href`` points to the
        product page.
        """
        soup = BeautifulSoup(page_html, "lxml")
        links: list[str] = []
        for a in soup.select("a.card"):
            href = a.get("href")
            if href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://www.futurepedia.io{href}")
        return links

    def _extract_there_an_ai_for_that_urls(self, page_html: str) -> list[str]:
        """Parse "There's An AI For That" for product URLs.

        The site lists products in ``div.product-item a``.
        """
        soup = BeautifulSoup(page_html, "lxml")
        links: list[str] = []
        for a in soup.select("div.product-item a"):
            href = a.get("href")
            if href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://theresanaiforthat.com{href}")
        return links

    def _extract_pricing_model(self, text: str) -> PricingModel | None:
        """Determine the pricing model from explicit tokens.

        Only exact tokens ``FREE``, ``FREEMIUM``, ``PAID``, ``ENTERPRISE`` are
        accepted. The search is case-insensitive but must match whole words.
        """
        match = re.search(r"\\b(FREE|FREEMIUM|PAID|ENTERPRISE)\\b", text, re.IGNORECASE)
        if not match:
            return None
        token = match.group(1).upper()
        return PricingModel[token]

    def _extract_product(self, html: str, url: str, source_name: str) -> Product | None:
        """Parse a product page and build a ``Product`` model.

        If required fields are missing or pricing cannot be determined the
        function returns ``None`` - the caller will treat this as a quarantine
        record.
        """
        soup = BeautifulSoup(html, "lxml")
        name_tag = soup.find("h1")
        startup_name = name_tag.get_text(strip=True) if name_tag else None
        if not startup_name:
            title = soup.title.string if soup.title else None
            startup_name = title.strip() if title else None
        if not startup_name:
            logger.warning(
                "product_missing_name",
                url=url,
                source=source_name,
            )
            return None
        pricing = self._extract_pricing_model(soup.get_text(" "))
        if pricing is None:
            logger.warning(
                "product_pricing_undetermined",
                url=url,
                source=source_name,
            )
            return None
        content = ProductContent(startupName=startup_name, pricingModel=pricing)
        provenance = SourceInfo(name=source_name, url=url)
        product = Product(
            content=content,
            source=provenance,
            collectedAt=datetime.now(UTC),
        )
        return product

    async def _process_product(self, url: str, source_name: str) -> Product | None:
        """Fetch a product page, extract data, and build a ``Product`` model."""
        # Use the pipeline to fetch the URL respecting the source's crawl method.
        crawled = await self.pipeline.crawl_source(self.pipeline.registry.get_source(source_name), url=url)
        if not crawled.is_success:
            logger.warning(
                "product_fetch_failed",
                url=url,
                error=crawled.error or f"HTTP {crawled.status_code}",
            )
            return None
        html = crawled.cleaned_content.html if crawled.cleaned_content else ""
        return self._extract_product(html, url, source_name)


    async def crawl(self, source_name: str) -> list[Product]:
        """Crawl a product source and return a list of validated ``Product`` models."""
        product_urls = await self._discover_product_urls(source_name)
        products: list[Product] = []
        semaphore = asyncio.Semaphore(5)
        async def worker(u: str):
            async with semaphore:
                prod = await self._process_product(u, source_name)
                if prod:
                    products.append(prod)
        await asyncio.gather(*(worker(u) for u in product_urls))
        return products
