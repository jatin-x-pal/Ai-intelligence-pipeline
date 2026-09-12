"""Crawler foundation for HTTP, browser-based ingestion, source registry, and pipeline."""

from src.crawlers.base import BaseCrawler, CrawlResult
from src.crawlers.browser import BrowserCrawler
from src.crawlers.http import HttpCrawler
from src.crawlers.pipeline import CrawledDocument, SourceCrawlPipeline
from src.crawlers.sources import (
    CrawlMethod,
    SourceCategory,
    SourceConfig,
    SourceRegistry,
    load_sources,
)
from src.crawlers.startup import StartupCrawler

__all__ = [
    "BaseCrawler",
    "BrowserCrawler",
    "CrawlMethod",
    "CrawlResult",
    "CrawledDocument",
    "HttpCrawler",
    "SourceCategory",
    "SourceConfig",
    "SourceCrawlPipeline",
    "SourceRegistry",
    "StartupCrawler",
    "load_sources",
]
