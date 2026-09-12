from datetime import UTC, datetime
from typing import Any

import pytest

from src.crawlers.http import HttpCrawler
from src.crawlers.pipeline import CrawledDocument, SourceCrawlPipeline
from src.crawlers.research import ResearchCrawler
from src.models.base import SourceInfo
from src.models.research_paper import ResearchPaper


class DummyFetchResult:
    def __init__(self, body: str):
        self.body = body
        self.status = 200
        self.error = None
        self.is_success = True


class DummyHttpCrawler(HttpCrawler):
    async def fetch(self, url: str, **kwargs: Any) -> DummyFetchResult:
        html = """
        <html>
          <head>
            <meta name=\"citation_author\" content=\"Alice Smith\" />
            <meta name=\"citation_author\" content=\"Bob Jones\" />
          </head>
          <body>
            <a href=\"https://github.com/example/repo\">Code</a>
          </body>
        </html>
        """
        return DummyFetchResult(body=html)


class DummyPipeline(SourceCrawlPipeline):
    def __init__(self):
        pass

    async def crawl_source(self, source_name: str, *, url: str | None = None) -> CrawledDocument:
        now = datetime.now(UTC)
        return CrawledDocument(
            source_name=source_name,
            source_category="research",  # type: ignore[arg-type]
            url=url or "https://example.com/paper",
            normalized_url="https://example.com/paper",
            crawl_method="http",  # type: ignore[arg-type]
            collected_at=now,
            status_code=200,
            is_success=True,
            cleaned_content=None,
            metadata=None,
            publication_date=now,
            is_fresh=None,
            is_duplicate=False,
            error=None,
        )

    def get_http_crawler(self) -> HttpCrawler:
        return DummyHttpCrawler()


@pytest.mark.asyncio
async def test_research_crawler_returns_valid_paper():
    pipeline = DummyPipeline()
    crawler = ResearchCrawler(pipeline=pipeline)
    paper: ResearchPaper | None = await crawler.crawl("ArXiv AI Recent")
    assert paper is not None
    content = paper.content
    assert content.title is not None
    assert content.authors == ["Alice Smith", "Bob Jones"]
    assert content.paper_url == "https://example.com/paper"
    assert content.github_url == "https://github.com/example/repo"
    assert content.github_stars is None
    assert isinstance(content.published_date, datetime)
    # Provenance checks
    assert isinstance(paper.source_info, SourceInfo)
    assert paper.source_info.name == "ArXiv AI Recent"
    assert paper.source_info.url == "https://example.com/paper"
