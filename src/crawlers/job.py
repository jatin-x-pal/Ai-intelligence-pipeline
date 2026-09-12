"""Deterministic job crawler implementation.


This module defines `JobCrawler` which follows the same architecture as
`StartupCrawler` and `ProductCrawler`. It discovers individual job posting URLs
from each enabled job source, fetches the detail page, extracts deterministic
fields required by the `Job` Pydantic model, enforces the 24-hour freshness
requirement, and respects the existing deduplication and provenance handling.
"""

import asyncio
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from src.crawlers.pipeline import CrawledDocument, SourceCrawlPipeline
from src.models.base import SourceInfo
from src.models.job import Job, JobContent
from src.utils.logging import get_logger

logger = get_logger(__name__)


class JobCrawler:
    """Crawler for the job category.

    It uses `SourceCrawlPipeline` to fetch index pages for each configured job
    source, discovers the URLs of individual job postings, and then builds a
    validated `Job` model for each posting.
    """

    def __init__(self, pipeline: SourceCrawlPipeline | None = None) -> None:
        self.pipeline = pipeline or SourceCrawlPipeline()
    # ---------------------------------------------------------------------
    # URL discovery helpers - each source has a small, deterministic selector.
    # ---------------------------------------------------------------------
    async def _discover_job_urls(self, source_name: str) -> list[str]:
        """Fetch the source index page and return a list of job-detail URLs.

        The discovery logic is source-specific and handled by private helper
        methods. If the index crawl fails or the source is unknown, an empty list
        is returned and a warning is logged.
        """
        crawled: CrawledDocument = await self.pipeline.crawl_source(source_name)
        if not crawled.is_success:
            logger.warning(
                "job_discovery_failed",
                source=source_name,
                error=crawled.error,
            )
            return []
        html = crawled.cleaned_content.html if crawled.cleaned_content else ""
        # Dispatch based on the source name - exact strings from sources.yaml.
        if "Work at a Startup AI" in source_name:
            return self._extract_work_at_startup_urls(html)
        if "RemoteOK AI" in source_name:
            return self._extract_remoteok_urls(html)
        if "Wellfound AI" in source_name:
            return self._extract_wellfound_urls(html)
        if "AIJobs.net" in source_name:
            return self._extract_aijobsnet_urls(html)
        if "WeWorkRemotely AI" in source_name:
            return self._extract_weworkremotely_urls(html)
        logger.warning("job_unknown_source", source=source_name)
        return []

    # ---- individual source selectors -------------------------------------------------
    def _extract_work_at_startup_urls(self, page_html: str) -> list[str]:
        """Parse *Work at a Startup* listing page for job URLs.

        The site lists cards whose anchor href contains ``/companies/``. The
        function normalises relative links to absolute URLs.
        """
        soup = BeautifulSoup(page_html, "html.parser")
        links: list[str] = []
        for a in soup.select("a[href*='/companies/']"):
            href = a.get("href")
            if href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://www.workatastartup.com{href}")
        return links

    def _extract_remoteok_urls(self, page_html: str) -> list[str]:
        """Parse *RemoteOK* listing page for job URLs.

        RemoteOK lists jobs in a table; each job title link contains the path
        ``/remote-ai-jobs/``. Relative links are expanded to the base domain.
        """
        soup = BeautifulSoup(page_html, "html.parser")
        links: list[str] = []
        for a in soup.select("a[href*='remote-ai-jobs']"):
            href = a.get("href")
            if href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://remoteok.com{href}")
        if not links:
            for a in soup.select("a[href*='/job/']"):
                href = a.get("href")
                if href:
                    if href.startswith("http"):
                        links.append(href)
                    else:
                        links.append(f"https://remoteok.com{href}")
        return links

    def _extract_wellfound_urls(self, page_html: str) -> list[str]:
        """Parse *Wellfound* (formerly AngelList) job listing page.

        Job links contain ``/role/`` in the path.
        """
        soup = BeautifulSoup(page_html, "html.parser")
        links: list[str] = []
        for a in soup.select("a[href*='/role/']"):
            href = a.get("href")
            if href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://wellfound.com{href}")
        return links

    def _extract_aijobsnet_urls(self, page_html: str) -> list[str]:
        """Parse *AIJobs.net* listing page.

        The site uses cards with class ``job-card``; the anchor points to the
        detail page and usually contains ``/jobs/``.
        """
        soup = BeautifulSoup(page_html, "html.parser")
        links: list[str] = []
        for a in soup.select("a[href*='/jobs/']"):
            href = a.get("href")
            if href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://aijobs.net{href}")
        return links

    def _extract_weworkremotely_urls(self, page_html: str) -> list[str]:
        """Parse *WeWorkRemotely* AI listing page.

        Job links contain ``/remote-`` in the path.
        """
        soup = BeautifulSoup(page_html, "html.parser")
        links: list[str] = []
        for a in soup.select("a[href*='/remote-']"):
            href = a.get("href")
            if href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(f"https://weworkremotely.com{href}")
        return links

    # ---------------------------------------------------------------------
    # Extraction of deterministic fields from a job detail page.
    # ---------------------------------------------------------------------
    def _extract_job(self, html: str, url: str, source_name: str) -> Job | None:
        """Parse a job detail page and build a ``Job`` model.

        Returns ``None`` if any required deterministic field is missing.
        """
        soup = BeautifulSoup(html, "html.parser")

        # ----- company -----------------------------------------------------
        company = None
        og_company = soup.find("meta", property="og:site_name")
        if og_company and og_company.get("content"):
            company = og_company["content"].strip()
        if not company:
            comp_tag = soup.select_one("*[class*='company']")
            if comp_tag:
                company = comp_tag.get_text(strip=True)
        if not company:
            logger.warning("job_missing_company", url=url, source=source_name)
            return None

        # ----- role / title ------------------------------------------------
        title_tag = soup.find("h1")
        role_family = title_tag.get_text(strip=True) if title_tag else None
        # Combine fallback for missing title in one statement
        if not role_family and soup.title and soup.title.string:
            role_family = soup.title.string.strip()
        if not role_family:
            logger.warning("job_missing_title", url=url, source=source_name)
            return None

        # ----- remote status ------------------------------------------------
        text_blob = soup.get_text(separator=" ", strip=True).lower()
        is_remote = bool(re.search(r"\bremote\b", text_blob))

        # Placeholder date - will be replaced with authoritative publication date.
        # Placeholder date - will be replaced with authoritative publication date.
        placeholder_date = datetime.now(UTC)
        content = JobContent(
            company=company,
            date=placeholder_date,
            is_remote=is_remote,
            role_family=role_family,
        )
        provenance = SourceInfo(name=source_name, url=url)
        job = Job(content=content, source=provenance, collectedAt=datetime.now(UTC))
        return job

    # ---------------------------------------------------------------------
    async def _process_job(self, url: str, source_name: str) -> Job | None:
        """Fetch a job page, enforce freshness, and build a ``Job`` model.
        """
        source_obj = getattr(self.pipeline, "registry", None)
        source = source_obj.get_source(source_name) if source_obj and hasattr(source_obj, "get_source") else source_name
        crawled: CrawledDocument = await self.pipeline.crawl_source(source, url=url)
        if not crawled.is_success:
            logger.warning(
                "job_fetch_failed",
                url=url,
                error=crawled.error or f"HTTP {crawled.status_code}",
            )
            return None
        if crawled.is_duplicate:
            logger.info("job_duplicate_skipped", url=url, source=source_name)
            return None
        pub_date = crawled.publication_date
        if pub_date is None:
            logger.warning("job_missing_publication_date", url=url, source=source_name)
            return None
        now = datetime.now(UTC)
        if pub_date > now:
            logger.warning("job_future_publication_date", url=url, source=source_name)
            return None
        if getattr(crawled, "is_fresh", None) is False:
            logger.info("job_stale_skipped", url=url, source=source_name)
            return None
        html = crawled.cleaned_content.html if crawled.cleaned_content else ""
        job = self._extract_job(html, url, source_name)
        if job is None:
            return None
        job.content.date = pub_date
        return job

    # ---------------------------------------------------------------------
    async def crawl(self, source_name: str) -> list[Job]:
        """Crawl a job source and return a list of validated ``Job`` models.
        """
        job_urls = await self._discover_job_urls(source_name)
        jobs: list[Job] = []
        semaphore = asyncio.Semaphore(5)
        async def worker(u: str):
            async with semaphore:
                job = await self._process_job(u, source_name)
                if job:
                    jobs.append(job)
        await asyncio.gather(*(worker(u) for u in job_urls))
        return jobs
