# mypy: ignore-errors
"""Research paper crawler.

Implements a deterministic extraction workflow for the research paper source
category. No LLMs are used. The crawler relies on :class:`SourceCrawlPipeline`
to fetch raw HTML and then maps the deterministic metadata to the
:class:`ResearchPaper` model.
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from pydantic import ValidationError

from src.crawlers.pipeline import CrawledDocument, SourceCrawlPipeline
from src.extraction.metadata import extract_metadata
from src.models.base import SourceInfo
from src.models.research_paper import ResearchPaper, ResearchPaperContent


class ResearchCrawler:
    """Crawler for the research‑paper category.

    Uses :class:`SourceCrawlPipeline` to fetch a source URL and then maps the
    deterministic extraction results to a :class:`ResearchPaper` model.
    """

    def __init__(self, pipeline: SourceCrawlPipeline | None = None) -> None:
        self.pipeline = pipeline or SourceCrawlPipeline()

    async def _extract_authors(self, html: str) -> list[str]:
        """Extract author names from ``<meta name=\"citation_author\">`` tags.

        Returns an empty list if no such tags are present.
        """
        soup = BeautifulSoup(html, "lxml")
        authors: list[str] = []
        for tag in soup.find_all(
            "meta",
            attrs={"name": lambda n: n and "citation_author" in n.lower()},
        ):
            content = tag.get("content")
            if content:
                authors.append(content.strip())
        return authors

    def _extract_github_url(self, html: str) -> str | None:
        """Return an explicit GitHub URL if an ``<a>`` tag points to github.com.

        The heuristic follows the approved rule: only return a URL that is
        literally present in the page; never construct or infer one.
        """
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if "github.com" in href.lower() and href.startswith(("http://", "https://")):
                return href
        return None

    async def crawl(self, source_name: str) -> ResearchPaper | None:
        """Crawl a research‑paper source and return a validated ``ResearchPaper``.

        If required fields are missing or the crawl fails, ``None`` is returned.
        """
        # Step 1: use the generic pipeline to fetch the document
        crawled: CrawledDocument = await self.pipeline.crawl_source(source_name)

        # Fetch raw HTML to extract authors, GitHub URL, and deterministic metadata
        http_crawler = self.pipeline.get_http_crawler()
        fetch_result = await http_crawler.fetch(crawled.url)
        html_body = getattr(fetch_result, "body", "")
        # Deterministic metadata extraction
        extracted_meta = extract_metadata(html_body, source_url=crawled.url)
        title = extracted_meta.title or crawled.url
        paper_url = extracted_meta.canonical_url or crawled.url
        # Publication date is provided by the pipeline (already deterministic)
        published_date = crawled.publication_date
        # Validate required fields (title and publication date) per schema
        if not title or not published_date:
            return None
        # Provenance using existing ``SourceInfo`` model
        provenance = SourceInfo(name=crawled.source_name, url=crawled.url)

        # Extract authors and github URL deterministically
        authors = await self._extract_authors(html_body)
        github_url = self._extract_github_url(html_body)

        # Build the content model; ``github_stars`` is left as ``None`` per instruction
        try:
            content = ResearchPaperContent(
                title=title,
                authors=authors,
                paper_url=paper_url,
                github_url=github_url,
                github_stars=None,
                published_date=published_date,
            )
            paper = ResearchPaper(content=content, source_info=provenance)
        except ValidationError:
            return None

        return paper
