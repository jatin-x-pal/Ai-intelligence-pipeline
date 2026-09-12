
import pytest

from src.crawlers.http import HttpCrawler
from src.crawlers.startup import StartupCrawler
from src.models.startup import Startup

# Mock HTML for Y Combinator startup detail page
YCOMBINATOR_DETAIL_HTML = """
<html><head><title>Test Startup</title></head>
<body>
<h1>Test Startup Inc.</h1>
<p>Employees: 42</p>
</body></html>
"""

# Mock HTML for Techstars startup detail page (different structure)
TECHSTARS_DETAIL_HTML = """
<html><head><title>Another Startup</title></head>
<body>
<h1>Another Startup Ltd.</h1>
<div>We have 10 employees working remotely.</div>
</body></html>
"""

@pytest.mark.asyncio
async def test_startup_crawler_ycombinator(monkeypatch):
    async def mock_fetch(url: str):
        return YCOMBINATOR_DETAIL_HTML
    monkeypatch.setattr(HttpCrawler, "fetch", staticmethod(mock_fetch))
    source_config = {
        "category": "startup",
        "name": "Y Combinator AI",
        "url": "https://example.com/ycombinator",
        "crawl_method": "http",
    }
    crawler = StartupCrawler(source_config)
    results = await crawler.crawl()
    assert len(results) == 1
    startup: Startup = results[0].model
    assert startup.entityName == "Test Startup Inc."
    assert startup.data.employeeCount == 42

@pytest.mark.asyncio
async def test_startup_crawler_techstars(monkeypatch):
    async def mock_fetch(url: str):
        return TECHSTARS_DETAIL_HTML
    monkeypatch.setattr(HttpCrawler, "fetch", staticmethod(mock_fetch))
    source_config = {
        "category": "startup",
        "name": "Techstars AI",
        "url": "https://example.com/techstars",
        "crawl_method": "http",
    }
    crawler = StartupCrawler(source_config)
    results = await crawler.crawl()
    assert len(results) == 1
    startup: Startup = results[0].model
    assert startup.entityName == "Another Startup Ltd."
    assert startup.data.employeeCount == 10
