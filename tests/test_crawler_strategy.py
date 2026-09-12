
import asyncio
from datetime import UTC, datetime

import pytest

from src.crawlers.base import CrawlResult
from src.crawlers.pipeline import CrawledDocument, SourceCrawlPipeline
from src.crawlers.sources import CrawlMethod, SourceCategory, SourceConfig, load_sources
from src.utils.retry import RetryConfig, calculate_backoff, parse_retry_after


# Mock crawlers for controlled responses
class MockHttpCrawler:
    def __init__(self, responses):
        self._responses = asyncio.Queue()
        for r in responses:
            self._responses.put_nowait(r)
        self.call_count = 0

    async def fetch(self, url: str, **kwargs):
        self.call_count += 1
        return await self._responses.get()

    async def close(self):
        pass

class MockBrowserCrawler:
    def __init__(self, response=None):
        # Provide a default successful CrawlResult if none supplied
        if response is None:
            response = CrawlResult(
                url="https://example.com",
                status=200,
                headers={},
                body="<html></html>",
                content_type="text/html",
            )
        self.response = response
        self.call_count = 0

    async def fetch(self, url: str, **kwargs):
        self.call_count += 1
        return self.response

    async def close(self):
        pass

# ... rest of file unchanged ...

@pytest.mark.asyncio
async def test_http_crawler_selection(monkeypatch):
    source = SourceConfig(
        name="Test HTTP",
        base_url="https://example.com",
        category=SourceCategory.NEWS,
        crawl_method=CrawlMethod.HTTP,
        enabled=True,
    )
    mock_result = CrawlResult(url="https://example.com", status=200, headers={}, body="<html></html>")
    mock_http = MockHttpCrawler([mock_result])
    monkeypatch.setattr(SourceCrawlPipeline, "get_http_crawler", lambda self: mock_http)
    pipeline = SourceCrawlPipeline()
    doc: CrawledDocument = await pipeline.crawl_source(source)
    assert doc.is_success
    assert mock_http.call_count == 1

@pytest.mark.asyncio
async def test_browser_crawler_selection(monkeypatch):
    source = SourceConfig(
        name="Test Browser",
        base_url="https://example.com",
        category=SourceCategory.NEWS,
        crawl_method=CrawlMethod.BROWSER,
        enabled=True,
    )
    mock_result = CrawlResult(url="https://example.com", status=200, headers={}, body="<html></html>")
    mock_browser = MockBrowserCrawler(mock_result)
    monkeypatch.setattr(SourceCrawlPipeline, "get_browser_crawler", lambda self: mock_browser)
    pipeline = SourceCrawlPipeline()
    doc = await pipeline.crawl_source(source)
    assert doc.is_success
    assert mock_browser.call_count == 1

@pytest.mark.asyncio
async def test_http_permanent_error_403(monkeypatch):
    source = SourceConfig(
        name="Permanent 403",
        base_url="https://example.com/blocked",
        category=SourceCategory.NEWS,
        crawl_method=CrawlMethod.HTTP,
        enabled=True,
    )
    perm_result = CrawlResult(url="https://example.com/blocked", status=403, headers={}, body="", error="Forbidden")
    mock_http = MockHttpCrawler([perm_result])
    monkeypatch.setattr(SourceCrawlPipeline, "get_http_crawler", lambda self: mock_http)
    pipeline = SourceCrawlPipeline()
    doc = await pipeline.crawl_source(source)
    assert not doc.is_success
    assert doc.status_code == 403
    assert mock_http.call_count == 1

def test_calculate_backoff_respects_retry_after():
    cfg = RetryConfig(max_retries=3, base_delay=1, exponential_factor=2, max_delay=30, jitter=False)
    delay = calculate_backoff(attempt=0, config=cfg, retry_after=12.5)
    assert delay == 12.5

def test_parse_retry_after_numeric_and_date():
    assert parse_retry_after("45") == 45.0
    future_date = "Wed, 31 Dec 2099 23:59:59 GMT"
    seconds = parse_retry_after(future_date)
    assert isinstance(seconds, float) and seconds > 0

@pytest.mark.asyncio
async def test_rate_limit_and_concurrency(monkeypatch):
    # Create a source with rate limit 2/sec and max_concurrency 1
    source = SourceConfig(
        name="RateLimit Test",
        base_url="https://example.com",
        category=SourceCategory.NEWS,
        crawl_method=CrawlMethod.HTTP,
        enabled=True,
        rate_limit_per_second=2.0,
        max_concurrency=1,
        timeout_seconds=5.0,
    )
    # Mock HttpCrawler to return instant success
    mock_result = CrawlResult(url="https://example.com", status=200, headers={}, body="<html></html>")
    mock_http = MockHttpCrawler([mock_result, mock_result])
    monkeypatch.setattr(SourceCrawlPipeline, "get_http_crawler", lambda self: mock_http)
    pipeline = SourceCrawlPipeline()
    start = datetime.now(UTC)
    doc1 = await pipeline.crawl_source(source)
    doc2 = await pipeline.crawl_source(source)
    elapsed = (datetime.now(UTC) - start).total_seconds()
    assert doc1.is_success and doc2.is_success
    # With 2/sec rate limit, second call should be at least 0.5s later
    assert elapsed >= 0.4

@pytest.mark.asyncio
async def test_timeout_enforced_in_http_crawler(monkeypatch):
    from src.crawlers.http import HttpCrawler
    crawler = HttpCrawler(timeout=0.01, max_concurrency=1)
    class SlowSession:
        async def get(self, *args, **kwargs):
            raise TimeoutError()
    crawler._session = SlowSession()
    source = SourceConfig(
        name="Timeout Test",
        base_url="https://example.com",
        category=SourceCategory.NEWS,
        crawl_method=CrawlMethod.HTTP,
        enabled=True,
        timeout_seconds=0.01,
    )
    pipeline = SourceCrawlPipeline(http_crawler=crawler)
    doc = await pipeline.crawl_source(source)
    assert not doc.is_success
    assert doc.status_code == 0

import pytest

from src.crawlers.http import HttpCrawler


# Simple mock crawler that returns a successful CrawlResult instantly
class MockSuccessCrawler(HttpCrawler):
    async def fetch(self, url: str, **kwargs) -> CrawlResult:
        return CrawlResult(
            url=url,
            status=200,
            headers={"content-type": "text/html"},
            body="<html><head><title>Test</title></head><body>OK</body></html>",
            content_type="text/html",
        )

class MockBrowserCrawler:
    def __init__(self, response=None):
        # Provide a default successful CrawlResult if none supplied
        if response is None:
            response = CrawlResult(
                url="https://example.com",
                status=200,
                headers={},
                body="<html></html>",
                content_type="text/html",
            )
        self.response = response
        self.call_count = 0

    async def fetch(self, url: str, **kwargs):
        self.call_count += 1
        return self.response

    async def close(self):
        pass

@pytest.mark.asyncio
async def test_crawler_selection():
    registry = load_sources()
    http_source = next(s for s in registry.sources if s.crawl_method == CrawlMethod.HTTP)
    browser_source = next(s for s in registry.sources if s.crawl_method == CrawlMethod.BROWSER)
    pipeline = SourceCrawlPipeline(registry=registry, http_crawler=MockSuccessCrawler(), browser_crawler=MockBrowserCrawler())
    assert isinstance(pipeline.get_crawler_for_source(http_source), MockSuccessCrawler)
    assert isinstance(pipeline.get_crawler_for_source(browser_source), MockBrowserCrawler)

@pytest.mark.asyncio
async def test_rate_limit_and_concurrency():
    from src.crawlers.sources import CrawlMethod, SourceCategory, SourceConfig
    test_source = SourceConfig(
        name="Test Source",
        base_url="https://example.com",
        category=SourceCategory.NEWS,
        crawl_method=CrawlMethod.HTTP,
        enabled=True,
        rate_limit_per_second=2.0,
        max_concurrency=1,
        timeout_seconds=10.0,
    )
    pipeline = SourceCrawlPipeline(registry=None, http_crawler=MockSuccessCrawler())
    # inject a dummy registry with the test source
    pipeline.registry = type("Reg", (), {"get_source": lambda self, name: test_source})()
    start = datetime.now(UTC)
    doc1 = await pipeline.crawl_source(test_source)
    doc2 = await pipeline.crawl_source(test_source)
    elapsed = (datetime.now(UTC) - start).total_seconds()
    assert isinstance(doc1, CrawledDocument)
    assert isinstance(doc2, CrawledDocument)
    # With rate limit 2/sec, the second request should be at least 0.5s later
    assert elapsed >= 0.4

@pytest.mark.asyncio
async def test_http_blocked_page_detection(monkeypatch):
    from src.crawlers.http import HttpCrawler
    # Mock session returning a blocked page (e.g., CAPTCHA) with status 200
    class BlockedSession:
        async def get(self, *args, **kwargs):
            class Resp:
                status = 200
                headers = {}
                content_type = "text/html"
                async def text(self, errors=None):
                    return "<html><body>CAPTCHA required</body></html>"
                async def __aenter__(self):
                    return self
                async def __aexit__(self, exc_type, exc, tb):
                    pass
                @property
                def url(self):
                    return args[0]
            return Resp()
    crawler = HttpCrawler(timeout=5.0, max_concurrency=1)
    crawler._session = BlockedSession()
    source = SourceConfig(
        name="Blocked Test",
        base_url="https://example.com",
        category=SourceCategory.NEWS,
        crawl_method=CrawlMethod.HTTP,
        enabled=True,
        timeout_seconds=5.0,
    )
    pipeline = SourceCrawlPipeline(http_crawler=crawler)
    doc = await pipeline.crawl_source(source)
    assert not doc.is_success
    assert doc.error == "Blocked page detected"
