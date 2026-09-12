"""Tests for source configuration models and the YAML source registry."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.crawlers.sources import (
    CrawlMethod,
    SourceCategory,
    SourceConfig,
    SourceRegistry,
    load_sources,
)


class TestSourceConfigValidation:
    """Tests for validating individual SourceConfig instances."""

    def test_valid_source_config(self) -> None:
        cfg = SourceConfig(
            name="Test Source",
            base_url="https://example.com/feed",
            category=SourceCategory.NEWS,
            crawl_method=CrawlMethod.HTTP,
            enabled=True,
            rate_limit_per_second=2.5,
            max_concurrency=4,
            timeout_seconds=30.0,
            headers={"User-Agent": "TestBot/1.0"},
        )
        assert cfg.name == "Test Source"
        assert cfg.base_url == "https://example.com/feed"
        assert cfg.category == SourceCategory.NEWS
        assert cfg.crawl_method == CrawlMethod.HTTP
        assert cfg.enabled is True
        assert cfg.rate_limit_per_second == 2.5
        assert cfg.max_concurrency == 4
        assert cfg.timeout_seconds == 30.0
        assert cfg.headers["User-Agent"] == "TestBot/1.0"

    def test_base_url_normalized_automatically(self) -> None:
        cfg = SourceConfig(
            name="Normalized URL Test",
            base_url="HTTPS://EXAMPLE.COM:443/Feed/?utm_source=test#anchor",
            category=SourceCategory.PRODUCT,
        )
        # Scheme/host lowercased, default port stripped, fragment and tracking param stripped
        assert cfg.base_url == "https://example.com/Feed/"

    def test_blank_name_fails(self) -> None:
        with pytest.raises(ValidationError, match="Source name cannot be blank"):
            SourceConfig(
                name="   ",
                base_url="https://example.com",
                category=SourceCategory.STARTUP,
            )

    def test_invalid_url_fails(self) -> None:
        with pytest.raises(ValidationError, match="Invalid or unsupported source URL"):
            SourceConfig(
                name="Bad URL",
                base_url="ftp://invalid-scheme.com",
                category=SourceCategory.NEWS,
            )

        with pytest.raises(ValidationError, match="Invalid or unsupported source URL"):
            SourceConfig(
                name="Empty URL",
                base_url="",
                category=SourceCategory.JOB,
            )

    def test_invalid_category_fails(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(
                name="Bad Category",
                base_url="https://example.com",
                category="invalid_category",  # type: ignore[arg-type]
            )

    def test_invalid_crawl_method_fails(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(
                name="Bad Method",
                base_url="https://example.com",
                category=SourceCategory.NEWS,
                crawl_method="selenium",  # type: ignore[arg-type]
            )

    def test_negative_rates_or_concurrency_fail(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(
                name="Negative Rate",
                base_url="https://example.com",
                category=SourceCategory.NEWS,
                rate_limit_per_second=-1.0,
            )

        with pytest.raises(ValidationError):
            SourceConfig(
                name="Zero Concurrency",
                base_url="https://example.com",
                category=SourceCategory.NEWS,
                max_concurrency=0,
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(
                name="Extra Field Test",
                base_url="https://example.com",
                category=SourceCategory.NEWS,
                unexpected_field="disallowed",  # type: ignore[call-arg]
            )


class TestSourceRegistryLoading:
    """Tests for loading and validating source configurations from YAML."""

    def test_load_default_sources_yaml(self) -> None:
        registry = load_sources()
        assert len(registry) >= 15
        categories = registry.get_categories()
        assert SourceCategory.STARTUP in categories
        assert SourceCategory.PRODUCT in categories
        assert SourceCategory.RESEARCH in categories
        assert SourceCategory.NEWS in categories
        assert SourceCategory.JOB in categories

    def test_news_and_job_sources_quota(self) -> None:
        registry = load_sources()
        news_sources = registry.get_sources(category=SourceCategory.NEWS)
        job_sources = registry.get_sources(category=SourceCategory.JOB)
        research_sources = registry.get_sources(category=SourceCategory.RESEARCH)

        # Assignment requirements: at least 5 news and 5 job sources, plus ArXiv / Papers With Code
        assert len(news_sources) >= 5
        assert len(job_sources) >= 5
        assert len(research_sources) >= 2

        # Check for ArXiv and Papers With Code presence
        names = [s.name.lower() for s in research_sources]
        assert any("arxiv" in name for name in names)
        assert any("papers with code" in name for name in names)

    def test_from_yaml_string(self) -> None:
        yaml_content = """
        sources:
          - name: "Inline News"
            base_url: "https://example.com/news"
            category: "news"
            crawl_method: "http"
            enabled: true
          - name: "Inline Jobs"
            base_url: "https://example.com/jobs"
            category: "job"
            crawl_method: "browser"
            enabled: false
        """
        registry = SourceRegistry.from_yaml(yaml_content)
        assert len(registry) == 2
        assert registry.get_source("Inline News") is not None
        assert registry.get_source("Inline Jobs") is not None

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            SourceRegistry.from_yaml(Path("non_existent_sources_file.yaml"))

    def test_malformed_yaml_raises_value_error(self) -> None:
        bad_yaml = "sources: [unclosed list"
        with pytest.raises(ValueError, match="Malformed YAML"):
            SourceRegistry.from_yaml(bad_yaml)

    def test_missing_sources_mapping_raises_value_error(self) -> None:
        invalid_yaml = "- a list instead of dict"
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            SourceRegistry.from_yaml(invalid_yaml)


class TestSourceRegistryFiltering:
    """Tests for filtering sources by category, enabled state, and crawl method."""

    @pytest.fixture
    def sample_registry(self) -> SourceRegistry:
        yaml_content = """
        sources:
          - name: "News Source 1"
            base_url: "https://news1.com"
            category: "news"
            crawl_method: "http"
            enabled: true
          - name: "News Source 2"
            base_url: "https://news2.com"
            category: "news"
            crawl_method: "browser"
            enabled: false
          - name: "Job Source 1"
            base_url: "https://jobs1.com"
            category: "job"
            crawl_method: "http"
            enabled: true
          - name: "Startup Source 1"
            base_url: "https://startups1.com"
            category: "startup"
            crawl_method: "browser"
            enabled: true
        """
        return SourceRegistry.from_yaml(yaml_content)

    def test_filter_by_category(self, sample_registry: SourceRegistry) -> None:
        news = sample_registry.get_sources(category=SourceCategory.NEWS, enabled_only=False)
        assert len(news) == 2
        assert all(s.category == SourceCategory.NEWS for s in news)

        # String category lookup
        jobs = sample_registry.get_sources(category="job", enabled_only=False)
        assert len(jobs) == 1
        assert jobs[0].name == "Job Source 1"

    def test_filter_by_enabled_only(self, sample_registry: SourceRegistry) -> None:
        # Default is enabled_only=True
        enabled_news = sample_registry.get_sources(category=SourceCategory.NEWS)
        assert len(enabled_news) == 1
        assert enabled_news[0].name == "News Source 1"

        all_enabled = sample_registry.get_sources(enabled_only=True)
        assert len(all_enabled) == 3

    def test_filter_by_crawl_method(self, sample_registry: SourceRegistry) -> None:
        browser_sources = sample_registry.get_sources(crawl_method=CrawlMethod.BROWSER, enabled_only=False)
        assert len(browser_sources) == 2

        http_sources = sample_registry.get_sources(crawl_method="http", enabled_only=False)
        assert len(http_sources) == 2

    def test_get_source_by_name(self, sample_registry: SourceRegistry) -> None:
        src = sample_registry.get_source("news source 1")
        assert src is not None
        assert src.base_url == "https://news1.com/"

        assert sample_registry.get_source("Nonexistent Source") is None

    def test_registry_iteration_and_len(self, sample_registry: SourceRegistry) -> None:
        assert len(sample_registry) == 4
        names = [s.name for s in sample_registry]
        assert "Startup Source 1" in names
