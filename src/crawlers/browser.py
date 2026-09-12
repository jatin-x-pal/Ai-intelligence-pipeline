"""Playwright-based asynchronous browser crawler for JavaScript-rendered web pages."""

import asyncio
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    async_playwright,
)

from src.crawlers.base import BaseCrawler, CrawlResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


class BrowserCrawler(BaseCrawler):
    """Asynchronous crawler for heavy dynamic / JavaScript pages using Playwright."""

    def __init__(
        self,
        *,
        max_concurrency: int = 5,
        timeout: float = 30.0,
        headless: bool = True,
        user_agent: str | None = None,
        viewport: dict[str, int] | None = None,
        browser: Browser | None = None,
    ) -> None:
        """Initialize browser crawler.

        Args:
            max_concurrency: Maximum number of concurrent browser pages.
            timeout: Page navigation timeout in seconds.
            headless: Whether to launch browser in headless mode.
            user_agent: Custom User-Agent string.
            viewport: Viewport dimension dictionary e.g. {"width": 1280, "height": 800}.
            browser: Optional pre-existing Browser instance (for testing or reuse).
        """
        super().__init__(max_concurrency=max_concurrency, timeout=timeout)
        self.headless = headless
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        )
        self.viewport = viewport or {"width": 1280, "height": 800}
        self._browser = browser
        self._owns_browser = browser is None
        self._playwright: Playwright | None = None
        self._lock = asyncio.Lock()

    async def get_browser(self) -> Browser:
        """Return shared Browser instance, launching it if necessary."""
        async with self._lock:
            if self._browser is None:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                    ],
                )
                logger.info("browser_launched", headless=self.headless)
            return self._browser

    async def fetch(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        wait_for_selector: str | None = None,
        extra_headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> CrawlResult:
        """Navigate to URL and return the rendered DOM.

        Args:
            url: Target URL to open.
            wait_until: Navigation wait condition ('load', 'domcontentloaded', 'networkidle').
            wait_for_selector: Optional CSS selector to wait for before extracting HTML.
            extra_headers: Additional HTTP headers to set on the context.
            **kwargs: Extra parameters ignored or passed to page.goto.

        Returns:
            A CrawlResult containing rendered HTML, status, and headers.
        """
        timeout_ms = int(self.timeout * 1000)

        # Bounded concurrency: hold semaphore while browser page is active
        async with self._semaphore:
            browser = await self.get_browser()
            context: BrowserContext | None = None
            page: Page | None = None

            try:
                context = await browser.new_context(
                    user_agent=self.user_agent,
                    viewport=self.viewport,  # type: ignore[arg-type]
                    extra_http_headers=extra_headers,
                )
                page = await context.new_page()

                logger.info("browser_navigating", url=url, wait_until=wait_until)
                response: Response | None = await page.goto(
                    url,
                    wait_until=wait_until,  # type: ignore[arg-type]
                    timeout=timeout_ms,
                )

                if wait_for_selector:
                    await page.wait_for_selector(wait_for_selector, timeout=timeout_ms)

                status = response.status if response is not None else 200
                raw_headers = await response.all_headers() if response is not None else {}
                headers = {k.lower(): v for k, v in raw_headers.items()}
                body = await page.content()
                content_type = headers.get("content-type", "text/html")

                return CrawlResult(
                    url=page.url,
                    status=status,
                    headers=headers,
                    body=body,
                    content_type=content_type,
                )

            except Exception as exc:  # noqa: BLE001
                logger.error("browser_crawl_failed", url=url, error=str(exc))
                return CrawlResult(
                    url=url,
                    status=0,
                    headers={},
                    body="",
                    error=f"{type(exc).__name__}: {exc}",
                )
            finally:
                if page is not None:
                    await page.close()
                if context is not None:
                    await context.close()

    async def close(self) -> None:
        """Close the browser and Playwright runtime if owned by this instance."""
        async with self._lock:
            if self._owns_browser and self._browser is not None:
                await self._browser.close()
                self._browser = None
                logger.info("browser_closed")

            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None
                logger.info("playwright_stopped")
