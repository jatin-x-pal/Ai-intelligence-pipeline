"""Configurable data source registry and validation for pipeline crawlers.

Loads and validates YAML configuration files describing target ingestion sources.
Avoids hardcoded sources in code and provides strongly-typed configuration
models for crawlers.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.utils.urls import is_valid_url, normalize_url


class SourceCategory(StrEnum):
    """Supported ingestion target categories."""

    STARTUP = "startup"
    PRODUCT = "product"
    RESEARCH = "research"
    NEWS = "news"
    JOB = "job"


class CrawlMethod(StrEnum):
    """Crawl mechanism required by the source."""

    HTTP = "http"
    BROWSER = "browser"


class SourceConfig(BaseModel):
    """Configuration model for a single ingestion source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., min_length=1, description="Human-readable unique name of the source")
    base_url: str = Field(..., description="Canonical base URL for the source")
    category: SourceCategory = Field(..., description="Entity category: startup, product, research, news, job")
    crawl_method: CrawlMethod = Field(default=CrawlMethod.HTTP, description="Crawl mechanism: http or browser")
    enabled: bool = Field(default=True, description="Whether this source is active for ingestion")
    rate_limit_per_second: float | None = Field(default=None, gt=0, description="Optional request rate limit")
    max_concurrency: int | None = Field(default=None, gt=0, description="Optional concurrency limit for this source")
    timeout_seconds: float | None = Field(default=None, gt=0, description="Optional HTTP/browser timeout in seconds")
    headers: dict[str, str] = Field(default_factory=dict, description="Optional custom HTTP headers")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Source name cannot be blank")
        return stripped

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not is_valid_url(v):
            raise ValueError(f"Invalid or unsupported source URL: {v!r}. Must be a valid HTTP/HTTPS URL.")
        return normalize_url(v)


class SourceRegistry(BaseModel):
    """Collection of configured pipeline ingestion sources."""

    model_config = ConfigDict(frozen=True)

    sources: list[SourceConfig] = Field(default_factory=list, description="Registered sources")

    @classmethod
    def from_yaml(cls, path_or_content: str | Path) -> SourceRegistry:
        """Load and validate sources from a YAML file or raw YAML string.

        Args:
            path_or_content: Path to .yaml file, or raw YAML string.

        Returns:
            Validated SourceRegistry instance.

        Raises:
            FileNotFoundError: If the specified file does not exist.
            ValueError: If the YAML content is invalid or missing required structure.
        """
        raw_text: str
        if isinstance(path_or_content, Path):
            if not path_or_content.is_file():
                raise FileNotFoundError(f"Source configuration file not found: {path_or_content}")
            raw_text = path_or_content.read_text(encoding="utf-8")
        elif isinstance(path_or_content, str):
            p = Path(path_or_content)
            if p.is_file():
                raw_text = p.read_text(encoding="utf-8")
            elif path_or_content.strip().endswith((".yaml", ".yml")):
                raise FileNotFoundError(f"Source configuration file not found: {path_or_content}")
            else:
                raw_text = path_or_content
        else:
            raise TypeError(f"Expected str or Path, got {type(path_or_content).__name__}")

        try:
            parsed = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise ValueError(f"Malformed YAML in source configuration: {exc}") from exc

        if not isinstance(parsed, dict) or "sources" not in parsed:
            raise ValueError("Source configuration must be a YAML mapping containing a 'sources' key")

        return cls.model_validate(parsed)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceRegistry:
        """Construct registry directly from a dictionary."""
        return cls.model_validate(data)

    def get_source(self, name: str) -> SourceConfig | None:
        """Find a source by name (case-insensitive)."""
        target = name.strip().lower()
        for src in self.sources:
            if src.name.lower() == target:
                return src
        return None

    def get_sources(
        self,
        *,
        category: SourceCategory | str | None = None,
        enabled_only: bool = True,
        crawl_method: CrawlMethod | str | None = None,
    ) -> list[SourceConfig]:
        """Filter sources by category, enabled status, and/or crawl method.

        Args:
            category: Optional category filter (e.g. 'news', 'job', SourceCategory.STARTUP).
            enabled_only: If True, only returns sources where enabled=True.
            crawl_method: Optional crawl method filter ('http' or 'browser').

        Returns:
            List of matching SourceConfig objects.
        """
        cat_filter = SourceCategory(category) if isinstance(category, str) else category
        method_filter = CrawlMethod(crawl_method) if isinstance(crawl_method, str) else crawl_method

        results: list[SourceConfig] = []
        for src in self.sources:
            if enabled_only and not src.enabled:
                continue
            if cat_filter is not None and src.category != cat_filter:
                continue
            if method_filter is not None and src.crawl_method != method_filter:
                continue
            results.append(src)
        return results

    def get_categories(self) -> set[SourceCategory]:
        """Return the set of all categories present in the registry."""
        return {s.category for s in self.sources}

    def __len__(self) -> int:
        return len(self.sources)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.sources)


def load_sources(config_path: str | Path | None = None) -> SourceRegistry:
    """Load default or custom source configuration registry.

    Args:
        config_path: Optional path to sources.yaml. If omitted, looks for config/sources.yaml.

    Returns:
        SourceRegistry containing all validated sources.
    """
    if config_path is None:
        # Default to workspace root config/sources.yaml
        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "sources.yaml"

    return SourceRegistry.from_yaml(config_path)
