import types
from datetime import UTC, datetime, timedelta

import pytest

from src.crawlers.news import NewsCrawler
from src.models.news import News


# Dummy objects to mimic pipeline output
class DummyCleaned:
    def __init__(self, clean_text: str = ""):
        self.clean_text = clean_text
        self.html = ""

class DummyMetadata:
    def __init__(self, title: str | None = None):
        self.title = title

class DummyCrawled:
    def __init__(self, *, is_success=True, is_fresh=True, title="Test Title", text="Article content.", pub_date=None, url="http://example.com/article"):
        self.is_success = is_success
        self.is_fresh = is_fresh
        self.cleaned_content = DummyCleaned(clean_text=text)
        self.metadata = DummyMetadata(title=title)
        self.publication_date = pub_date or datetime.now(UTC)
        self.url = url
        self.status_code = 200
        self.error = None

class DummyPipeline:
    def __init__(self, discovery_urls: list[str] | None = None, article_success: bool = True, article_fresh: bool = True, article_title: str | None = "Test Title", article_text: str = "Article content.", pub_date: datetime | None = None):
        self.discovery_urls = discovery_urls or []
        self.article_success = article_success
        self.article_fresh = article_fresh
        self.article_title = article_title
        self.article_text = article_text
        self.pub_date = pub_date

    async def crawl_source(self, source_or_name, *, url=None):
        # Discovery phase (url is None)
        if url is None:
            dummy = DummyCrawled(is_success=True, is_fresh=True, title=None, text="")
            dummy.cleaned_content = types.SimpleNamespace(html="<a href='http://example.com/a1'>Link1</a><a href='http://example.com/a2'>Link2</a>")
            dummy.metadata = types.SimpleNamespace()
            dummy.publication_date = None
            return dummy
        # Article fetch phase
        return DummyCrawled(
            is_success=self.article_success,
            is_fresh=self.article_fresh,
            title=self.article_title,
            text=self.article_text,
            pub_date=self.pub_date,
        )

    # Registry mock – needed for source lookup in _process_article
    class Registry:
        @staticmethod
        def get_source(name):
            return name

    @property
    def registry(self):
        return self.Registry()

# Helper to monkey‑patch discovery method
async def fake_discover(self, source_name):
    return self.pipeline.discovery_urls or ["http://example.com/article"]

@pytest.mark.asyncio
async def test_news_crawler_valid_article():
    crawler = NewsCrawler(pipeline=DummyPipeline())
    NewsCrawler._discover_news_urls = fake_discover
    results = await crawler.crawl("MIT Technology Review AI")
    assert isinstance(results, list)
    assert len(results) == 1
    news: News = results[0]
    assert news.content.title == "Test Title"
    assert "Article content" in news.content.text

@pytest.mark.asyncio
async def test_news_crawler_stale_article():
    crawler = NewsCrawler(pipeline=DummyPipeline(article_fresh=False))
    NewsCrawler._discover_news_urls = fake_discover
    results = await crawler.crawl("MIT Technology Review AI")
    assert results == []

@pytest.mark.asyncio
async def test_news_crawler_missing_title():
    crawler = NewsCrawler(pipeline=DummyPipeline(article_title=None))
    NewsCrawler._discover_news_urls = fake_discover
    results = await crawler.crawl("MIT Technology Review AI")
    assert results == []

@pytest.mark.asyncio
async def test_news_crawler_multiple_urls():
    pipeline = DummyPipeline(discovery_urls=["http://example.com/a1", "http://example.com/a2"])
    crawler = NewsCrawler(pipeline=pipeline)
    NewsCrawler._discover_news_urls = fake_discover
    results = await crawler.crawl("MIT Technology Review AI")
    assert len(results) == 2
    titles = {n.content.title for n in results}
    assert titles == {"Test Title"}

@pytest.mark.asyncio
async def test_news_crawler_duplicate_url():
    pipeline = DummyPipeline(discovery_urls=["http://example.com/dup", "http://example.com/dup"])
    crawler = NewsCrawler(pipeline=pipeline)
    NewsCrawler._discover_news_urls = fake_discover
    results = await crawler.crawl("MIT Technology Review AI")
    # Duplicate URLs should be logged and skipped, resulting in a single entry
    assert len(results) == 1

@pytest.mark.asyncio
async def test_news_crawler_future_date():
    future = datetime.now(UTC) + timedelta(days=1)
    pipeline = DummyPipeline(pub_date=future)
    crawler = NewsCrawler(pipeline=pipeline)
    NewsCrawler._discover_news_urls = fake_discover
    results = await crawler.crawl("MIT Technology Review AI")
    assert results == []

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Missing publication date not yet supported")
async def test_news_crawler_missing_date():
    pipeline = DummyPipeline(pub_date=None)
    crawler = NewsCrawler(pipeline=pipeline)
    NewsCrawler._discover_news_urls = fake_discover
    results = await crawler.crawl("MIT Technology Review AI")
    assert results == []

@pytest.mark.asyncio
async def test_news_crawler_provenance():
    pipeline = DummyPipeline()
    crawler = NewsCrawler(pipeline=pipeline)
    NewsCrawler._discover_news_urls = fake_discover
    results = await crawler.crawl("TechCrunch AI")
    assert results
    news: News = results[0]
    assert news.source.name == "TechCrunch AI"
    assert news.source.url.startswith("http")
