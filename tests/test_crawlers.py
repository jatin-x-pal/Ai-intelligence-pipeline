"""Unit and integration tests for async crawler foundation.

Tests cover:
- Success responses (status, headers, body, is_success)
- Timeouts and transient network errors
- Retries with exponential backoff and jitter
- 429 Rate limiting and Retry-After header parsing
- Non-retryable permanent client errors (400, 401, 403, 404)
- Bounded concurrency enforcement via Semaphore
- Session reuse across multiple requests
- BaseCrawler interface and CrawlResult data structure
- BrowserCrawler interface and lifecycle
"""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from src.crawlers import BrowserCrawler, CrawlResult, HttpCrawler
from src.utils.retry import (
    MaxRetriesExceededError,
    PermanentHttpError,
    RetryConfig,
    calculate_backoff,
    is_permanent_status,
    is_retryable_status,
    parse_retry_after,
)


# =============================================================================
# Helper Fixtures: In-Process Local Aiohttp Test Server
# =============================================================================
@pytest.fixture
async def mock_server():
    """Spin up an in-process aiohttp test server for deterministic HTTP tests."""
    app = web.Application()
    call_counts: dict[str, int] = {}

    async def handle_success(request: web.Request) -> web.Response:
        return web.Response(
            text="<html><body>Success</body></html>",
            content_type="text/html",
            headers={"X-Test-Header": "pipeline-test"},
        )

    async def handle_slow(request: web.Request) -> web.Response:
        await asyncio.sleep(0.5)
        return web.Response(text="slow response")

    async def handle_transient(request: web.Request) -> web.Response:
        key = "transient"
        call_counts[key] = call_counts.get(key, 0) + 1
        if call_counts[key] < 3:
            return web.Response(status=503, text="Service Unavailable")
        return web.Response(status=200, text="Recovered")

    async def handle_always_500(request: web.Request) -> web.Response:
        key = "always_500"
        call_counts[key] = call_counts.get(key, 0) + 1
        return web.Response(status=500, text="Internal Server Error")

    async def handle_rate_limit(request: web.Request) -> web.Response:
        key = "rate_limit"
        call_counts[key] = call_counts.get(key, 0) + 1
        if call_counts[key] == 1:
            return web.Response(
                status=429,
                text="Too Many Requests",
                headers={"Retry-After": "0.1"},
            )
        return web.Response(status=200, text="Rate Limit Passed")

    async def handle_not_found(request: web.Request) -> web.Response:
        key = "not_found"
        call_counts[key] = call_counts.get(key, 0) + 1
        return web.Response(status=404, text="Not Found")

    async def handle_forbidden(request: web.Request) -> web.Response:
        key = "forbidden"
        call_counts[key] = call_counts.get(key, 0) + 1
        return web.Response(status=403, text="Forbidden")

    active_requests = 0
    max_observed_active = 0

    async def handle_concurrency(request: web.Request) -> web.Response:
        nonlocal active_requests, max_observed_active
        active_requests += 1
        max_observed_active = max(max_observed_active, active_requests)
        await asyncio.sleep(0.05)
        active_requests -= 1
        return web.Response(text="concurrency ok")

    app.router.add_get("/success", handle_success)
    app.router.add_get("/slow", handle_slow)
    app.router.add_get("/transient", handle_transient)
    app.router.add_get("/always-500", handle_always_500)
    app.router.add_get("/rate-limit", handle_rate_limit)
    app.router.add_get("/not-found", handle_not_found)
    app.router.add_get("/forbidden", handle_forbidden)
    app.router.add_get("/concurrency", handle_concurrency)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    server_port = site._server.sockets[0].getsockname()[1]
    base_url = f"http://127.0.0.1:{server_port}"

    class ServerContext:
        url = base_url
        counts = call_counts

        def get_max_active(self) -> int:
            return max_observed_active

    yield ServerContext()

    await runner.cleanup()


# =============================================================================
# 1. Retry Utilities Tests
# =============================================================================
class TestRetryUtilities:
    """Tests for Retry-After parsing, status categorization, and backoff calculation."""

    def test_retryable_status_codes(self) -> None:
        for status in [408, 429, 500, 502, 503, 504]:
            assert is_retryable_status(status) is True
        for status in [200, 201, 301, 400, 401, 403, 404]:
            assert is_retryable_status(status) is False

    def test_permanent_status_codes(self) -> None:
        for status in [400, 401, 403, 404]:
            assert is_permanent_status(status) is True
        for status in [200, 408, 429, 500]:
            assert is_permanent_status(status) is False

    def test_parse_retry_after_numeric(self) -> None:
        assert parse_retry_after("120") == 120.0
        assert parse_retry_after("0.5") == 0.5
        assert parse_retry_after("-10") == 0.0

    def test_parse_retry_after_http_date(self) -> None:
        future_dt = datetime.now(UTC) + timedelta(seconds=60)
        formatted_date = format_datetime(future_dt, usegmt=True)
        parsed = parse_retry_after(formatted_date)
        assert parsed is not None
        assert 50.0 <= parsed <= 70.0

    def test_parse_retry_after_invalid(self) -> None:
        assert parse_retry_after(None) is None
        assert parse_retry_after("") is None
        assert parse_retry_after("not-a-valid-date-or-number") is None

    def test_calculate_backoff_exponential(self) -> None:
        config = RetryConfig(base_delay=1.0, exponential_factor=2.0, max_delay=10.0, jitter=False)
        assert calculate_backoff(0, config) == 1.0
        assert calculate_backoff(1, config) == 2.0
        assert calculate_backoff(2, config) == 4.0
        assert calculate_backoff(3, config) == 8.0
        assert calculate_backoff(4, config) == 10.0  # Capped at max_delay

    def test_calculate_backoff_with_retry_after(self) -> None:
        config = RetryConfig(base_delay=1.0, max_delay=30.0, jitter=False)
        assert calculate_backoff(0, config, retry_after=5.0) == 5.0
        # When capped
        assert calculate_backoff(0, config, retry_after=50.0) == 30.0

    def test_calculate_backoff_with_jitter(self) -> None:
        config = RetryConfig(base_delay=2.0, max_delay=10.0, jitter=True)
        for _ in range(20):
            val = calculate_backoff(1, config)
            assert 2.0 <= val <= 4.0  # 50% to 100% of 4.0


# =============================================================================
# 2. BaseCrawler & CrawlResult Tests
# =============================================================================
class TestBaseCrawler:
    """Tests for BaseCrawler abstraction and CrawlResult dataclass."""

    def test_crawl_result_properties(self) -> None:
        res_ok = CrawlResult(url="https://example.com", status=200, body="OK")
        assert res_ok.is_success is True
        assert res_ok.error is None

        res_fail = CrawlResult(url="https://example.com", status=500, error="HTTP 500")
        assert res_fail.is_success is False

    def test_base_crawler_validation(self) -> None:
        with pytest.raises(ValueError, match="max_concurrency must be at least 1"):
            HttpCrawler(max_concurrency=0)

        with pytest.raises(ValueError, match="timeout must be greater than 0"):
            HttpCrawler(timeout=0)


# =============================================================================
# 3. HttpCrawler: Success, Concurrency, and Session Reuse Tests
# =============================================================================
class TestHttpCrawlerBasics:
    """Tests basic success, headers, session lifecycle, and concurrency."""

    async def test_http_fetch_success(self, mock_server) -> None:
        async with HttpCrawler(timeout=5.0) as crawler:
            result = await crawler.fetch(f"{mock_server.url}/success")
            assert result.is_success is True
            assert result.status == 200
            assert "Success" in result.body
            assert result.headers.get("x-test-header") == "pipeline-test"
            assert result.content_type == "text/html"

    async def test_session_reuse(self, mock_server) -> None:
        async with HttpCrawler(timeout=5.0) as crawler:
            session_1 = await crawler.get_session()
            await crawler.fetch(f"{mock_server.url}/success")
            session_2 = await crawler.get_session()
            await crawler.fetch(f"{mock_server.url}/success")

            # Must be the exact same session instance
            assert session_1 is session_2
            assert not session_1.closed

        # After exiting context, session must be closed
        assert session_1.closed

    async def test_bounded_concurrency(self, mock_server) -> None:
        concurrency_limit = 2
        async with HttpCrawler(max_concurrency=concurrency_limit, timeout=5.0) as crawler:
            tasks = [crawler.fetch(f"{mock_server.url}/concurrency") for _ in range(6)]
            results = await asyncio.gather(*tasks)

            assert len(results) == 6
            assert all(r.status == 200 for r in results)
            # The server must not have observed active concurrency above the limit
            assert mock_server.get_max_active() <= concurrency_limit


# =============================================================================
# 4. HttpCrawler: Timeouts, Retries, 429, and Error Handling
# =============================================================================
class TestHttpCrawlerRetriesAndErrors:
    """Tests transient retries, permanent errors, timeouts, and rate limits."""

    async def test_timeout_handling(self, mock_server) -> None:
        fast_retry = RetryConfig(max_retries=1, base_delay=0.01, jitter=False)
        async with HttpCrawler(timeout=0.1, retry_config=fast_retry) as crawler:
            with pytest.raises(MaxRetriesExceededError) as exc_info:
                await crawler.fetch(f"{mock_server.url}/slow")

            assert "Retries exhausted" in str(exc_info.value)
            assert exc_info.value.attempts == 2

    async def test_retries_transient_status_then_succeeds(self, mock_server) -> None:
        fast_retry = RetryConfig(max_retries=3, base_delay=0.01, jitter=False)
        async with HttpCrawler(retry_config=fast_retry) as crawler:
            result = await crawler.fetch(f"{mock_server.url}/transient")
            assert result.status == 200
            assert "Recovered" in result.body
            assert mock_server.counts["transient"] == 3

    async def test_retries_exhausted_returns_or_raises(self, mock_server) -> None:
        fast_retry = RetryConfig(max_retries=2, base_delay=0.01, jitter=False)

        # raise_for_status=False returns CrawlResult with error
        async with HttpCrawler(retry_config=fast_retry) as crawler:
            result = await crawler.fetch(f"{mock_server.url}/always-500", raise_for_status=False)
            assert result.status == 500
            assert result.is_success is False
            assert "HTTP 500" in (result.error or "")
            assert mock_server.counts["always_500"] == 3

        # raise_for_status=True raises MaxRetriesExceededError
        async with HttpCrawler(retry_config=fast_retry) as crawler:
            with pytest.raises(MaxRetriesExceededError) as exc_info:
                await crawler.fetch(f"{mock_server.url}/always-500", raise_for_status=True)
            assert exc_info.value.last_status == 500

    async def test_no_blind_retry_on_permanent_errors(self, mock_server) -> None:
        fast_retry = RetryConfig(max_retries=3, base_delay=0.01, jitter=False)
        async with HttpCrawler(retry_config=fast_retry) as crawler:
            # 404 Not Found — must not retry!
            res_404 = await crawler.fetch(f"{mock_server.url}/not-found", raise_for_status=False)
            assert res_404.status == 404
            assert mock_server.counts["not_found"] == 1  # Exactly 1 attempt

            # 403 Forbidden with raise_for_status=True — raises PermanentHttpError immediately
            with pytest.raises(PermanentHttpError) as exc_info:
                await crawler.fetch(f"{mock_server.url}/forbidden", raise_for_status=True)
            assert exc_info.value.status == 403
            assert mock_server.counts["forbidden"] == 1  # Exactly 1 attempt

    async def test_rate_limit_429_respects_retry_after(self, mock_server) -> None:
        fast_retry = RetryConfig(max_retries=2, base_delay=0.01, jitter=False)
        async with HttpCrawler(retry_config=fast_retry) as crawler:
            start_time = asyncio.get_event_loop().time()
            result = await crawler.fetch(f"{mock_server.url}/rate-limit")
            elapsed = asyncio.get_event_loop().time() - start_time

            assert result.status == 200
            assert "Rate Limit Passed" in result.body
            assert mock_server.counts["rate_limit"] == 2
            # Verify it waited at least ~0.1s due to Retry-After
            assert elapsed >= 0.09


# =============================================================================
# 5. BrowserCrawler: Interface, Resource Management, and Concurrency Tests
# =============================================================================
class TestBrowserCrawler:
    """Tests for Playwright BrowserCrawler interface and lifecycle."""

    async def test_browser_crawler_interface_with_mock(self) -> None:
        # Mock Playwright Page, Context, and Browser
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.all_headers = AsyncMock(return_value={"content-type": "text/html"})

        mock_page = MagicMock()
        mock_page.url = "https://example.com/rendered"
        mock_page.goto = AsyncMock(return_value=mock_response)
        mock_page.content = AsyncMock(return_value="<html><body>Rendered JS Content</body></html>")
        mock_page.close = AsyncMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        crawler = BrowserCrawler(max_concurrency=2, timeout=10.0, browser=mock_browser)

        async with crawler:
            result = await crawler.fetch("https://example.com/dynamic")
            assert result.is_success is True
            assert result.status == 200
            assert result.url == "https://example.com/rendered"
            assert "Rendered JS Content" in result.body
            assert result.content_type == "text/html"

            mock_page.goto.assert_awaited_once()
            mock_page.close.assert_awaited_once()
            mock_context.close.assert_awaited_once()

    async def test_browser_crawler_error_handling(self) -> None:
        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(side_effect=RuntimeError("Browser context crashed"))
        mock_context.close = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        async with BrowserCrawler(browser=mock_browser) as crawler:
            result = await crawler.fetch("https://crash.example.com")
            assert result.is_success is False
            assert result.status == 0
            assert "RuntimeError" in (result.error or "")

    async def test_browser_crawler_close_lifecycle(self) -> None:
        mock_browser = MagicMock()
        mock_browser.close = AsyncMock()

        crawler = BrowserCrawler(browser=mock_browser)
        # Injected browser is not closed by crawler if _owns_browser is False
        await crawler.close()
        mock_browser.close.assert_not_called()
