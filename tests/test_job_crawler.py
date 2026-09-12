from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.crawlers.job import JobCrawler

if TYPE_CHECKING:
    from src.models.job import JobContent
# Simple containers to mimic pipeline return objects
class SimpleCleanedContent:
    def __init__(self, html: str):
        self.html = html

class SimpleCrawledDocument:
    def __init__(
        self,
        *,
        is_success: bool = True,
        error: str | None = None,
        cleaned_content: SimpleCleanedContent | None = None,
        publication_date: datetime | None = None,
        is_fresh: bool | None = None,
        is_duplicate: bool = False,
        status_code: int = 200,
    ):
        self.is_success = is_success
        self.error = error
        self.cleaned_content = cleaned_content
        self.publication_date = publication_date
        self.is_fresh = is_fresh
        self.is_duplicate = is_duplicate
        self.status_code = status_code
        self.source_name = ""
        self.source_category = None
        self.url = ""
        self.normalized_url = ""
        self.crawl_method = None
        self.collected_at = datetime.now(UTC)

# Fake pipeline that returns predetermined documents based on call pattern
class FakePipeline:
    def __init__(self, discovery_html: str, job_html: str, pub_date: datetime, fresh: bool, duplicate: bool = False):
        self.discovery_html = discovery_html
        self.job_html = job_html
        self.pub_date = pub_date
        self.fresh = fresh
        self.duplicate = duplicate
        self._source = None

    def get_http_crawler(self):
        return None

    def get_browser_crawler(self):
        return None

    async def crawl_source(self, source_or_name, *, url: str | None = None):
        if url is None:
            cleaned = SimpleCleanedContent(self.discovery_html)
            return SimpleCrawledDocument(is_success=True, cleaned_content=cleaned)
        cleaned = SimpleCleanedContent(self.job_html)
        return SimpleCrawledDocument(
            is_success=True,
            cleaned_content=cleaned,
            publication_date=self.pub_date,
            is_fresh=self.fresh,
            is_duplicate=self.duplicate,
        )

DISCOVERY_HTML = """<html><body><a href=\"/job/123\">Job 1</a></body></html>"""
JOB_HTML_TEMPLATE = """<html><head><meta property='og:site_name' content='{company}'/></head><body><h1>{title}</h1>{remote_flag}</body></html>"""

def test_fresh_job_extracted():
    pub_date = datetime.now(UTC) - timedelta(hours=2)
    html = JOB_HTML_TEMPLATE.format(company="Acme Corp", title="AI Engineer", remote_flag="Remote work available")
    pipeline = FakePipeline(DISCOVERY_HTML, html, pub_date, fresh=True)
    crawler = JobCrawler(pipeline)  # type: ignore[arg-type]
    results: list[JobContent] = asyncio.run(crawler.crawl("RemoteOK AI"))
    assert len(results) == 1
    job = results[0]
    assert job.content.company == "Acme Corp"
    assert job.content.role_family == "AI Engineer"
    assert job.content.is_remote is True
    assert job.content.date.tzinfo == UTC

def test_stale_job_skipped():
    pub_date = datetime.now(UTC) - timedelta(days=2)
    html = JOB_HTML_TEMPLATE.format(company="Stale Corp", title="Senior AI", remote_flag="")
    pipeline = FakePipeline(DISCOVERY_HTML, html, pub_date, fresh=False)
    crawler = JobCrawler(pipeline)  # type: ignore[arg-type]
    results = asyncio.run(crawler.crawl("RemoteOK AI"))
    assert len(results) == 0

def test_future_publication_date_rejected():
    pub_date = datetime.now(UTC) + timedelta(hours=5)
    html = JOB_HTML_TEMPLATE.format(company="Future Corp", title="Future AI", remote_flag="Remote work")
    pipeline = FakePipeline(DISCOVERY_HTML, html, pub_date, fresh=True)
    crawler = JobCrawler(pipeline)  # type: ignore[arg-type]
    results = asyncio.run(crawler.crawl("RemoteOK AI"))
    assert len(results) == 0

def test_missing_company_quarantined():
    pub_date = datetime.now(UTC) - timedelta(hours=1)
    html = """<html><head></head><body><h1>Dev AI</h1></body></html>"""
    pipeline = FakePipeline(DISCOVERY_HTML, html, pub_date, fresh=True)
    crawler = JobCrawler(pipeline)  # type: ignore[arg-type]
    results = asyncio.run(crawler.crawl("RemoteOK AI"))
    assert len(results) == 0

def test_duplicate_url_logged_and_skipped():
    pub_date = datetime.now(UTC) - timedelta(hours=1)
    html = JOB_HTML_TEMPLATE.format(company="Dup Corp", title="Dup AI", remote_flag="Remote")
    pipeline = FakePipeline(DISCOVERY_HTML, html, pub_date, fresh=True, duplicate=True)
    crawler = JobCrawler(pipeline)  # type: ignore[arg-type]
    results = asyncio.run(crawler.crawl("RemoteOK AI"))
    assert len(results) == 0
