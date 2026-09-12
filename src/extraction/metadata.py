"""Deterministic HTML metadata extraction.

Extracts structured metadata (titles, canonical links, OpenGraph, Twitter cards,
standard meta tags, JSON-LD schemas) without LLM intervention.
Never invents data: missing attributes are preserved as None or empty containers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, FeatureNotFound, Tag


@dataclass(frozen=True)
class ExtractedMetadata:
    """Container for deterministic metadata extracted from an HTML document."""

    source_url: str | None = None
    title: str | None = None
    canonical_url: str | None = None
    description: str | None = None
    author: str | None = None
    site_name: str | None = None
    opengraph: dict[str, str] = field(default_factory=dict)
    twitter: dict[str, str] = field(default_factory=dict)
    meta_tags: dict[str, str] = field(default_factory=dict)
    json_ld: list[dict[str, Any]] = field(default_factory=list)


def _safe_str(val: Any) -> str | None:
    """Return stripped string or None if falsy."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def extract_metadata(html: str, *, source_url: str | None = None) -> ExtractedMetadata:
    """Extract deterministic metadata from HTML content.

    Safely parses HTML and retrieves:
    - Page title (falling back across <title>, og:title, twitter:title, <h1>)
    - Canonical URL (from <link rel="canonical"> or og:url)
    - Meta description (from og:description, meta description, twitter:description)
    - Author (from meta author, article:author, twitter:creator)
    - Site name (from og:site_name)
    - All OpenGraph (og:*) attributes
    - All Twitter (twitter:*) attributes
    - Standard meta tags (name -> content)
    - Structured JSON-LD documents (<script type="application/ld+json">)

    Args:
        html: Raw HTML string.
        source_url: Source URL for provenance tracking.

    Returns:
        ExtractedMetadata containing extracted metadata or None for missing fields.
    """
    if not html or not html.strip():
        return ExtractedMetadata(source_url=source_url)

    try:
        soup = BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        soup = BeautifulSoup(html, "html.parser")

    opengraph: dict[str, str] = {}
    twitter: dict[str, str] = {}
    meta_tags: dict[str, str] = {}

    # 1. Collect all <meta> tags
    for meta in soup.find_all("meta"):
        prop = meta.get("property")
        name = meta.get("name")
        content = meta.get("content")

        if not content:
            continue
        content_str = str(content).strip()
        if not content_str:
            continue

        if prop:
            prop_key = str(prop).strip().lower()
            if prop_key.startswith("og:"):
                opengraph[prop_key] = content_str
            elif prop_key.startswith("twitter:"):
                twitter[prop_key] = content_str
            else:
                meta_tags[prop_key] = content_str

        if name:
            name_key = str(name).strip().lower()
            if name_key.startswith("og:"):
                opengraph[name_key] = content_str
            elif name_key.startswith("twitter:"):
                twitter[name_key] = content_str
            else:
                meta_tags[name_key] = content_str

    # 2. Extract Title
    title: str | None = None
    title_tag = soup.find("title")
    if isinstance(title_tag, Tag) and title_tag.string:
        title = _safe_str(title_tag.string)

    if not title:
        title = opengraph.get("og:title") or twitter.get("twitter:title")

    if not title:
        h1_tag = soup.find("h1")
        if isinstance(h1_tag, Tag):
            title = _safe_str(h1_tag.get_text(strip=True))

    # 3. Extract Canonical URL
    canonical_url: str | None = None
    canonical_link = soup.find("link", attrs={"rel": lambda r: bool(r and "canonical" in str(r).lower())})
    if isinstance(canonical_link, Tag) and canonical_link.get("href"):
        canonical_url = _safe_str(canonical_link.get("href"))

    if not canonical_url:
        canonical_url = _safe_str(opengraph.get("og:url"))

    # 4. Extract Description
    description = (
        opengraph.get("og:description")
        or meta_tags.get("description")
        or twitter.get("twitter:description")
    )
    description = _safe_str(description)

    # 5. Extract Author
    author = (
        meta_tags.get("author")
        or opengraph.get("article:author")
        or twitter.get("twitter:creator")
    )
    author = _safe_str(author)

    # 6. Extract Site Name
    site_name = _safe_str(opengraph.get("og:site_name"))

    # 7. Extract JSON-LD blocks
    json_ld_blocks: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        content = script.string or script.get_text()
        if not content or not content.strip():
            continue
        try:
            parsed = json.loads(content.strip())
            if isinstance(parsed, dict):
                # Handle @graph patterns
                if "@graph" in parsed and isinstance(parsed["@graph"], list):
                    for item in parsed["@graph"]:
                        if isinstance(item, dict):
                            json_ld_blocks.append(item)
                else:
                    json_ld_blocks.append(parsed)
            elif isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        json_ld_blocks.append(item)
        except (json.JSONDecodeError, ValueError, TypeError):
            # Gracefully ignore corrupted or invalid JSON-LD without failing
            continue

    return ExtractedMetadata(
        source_url=source_url,
        title=title,
        canonical_url=canonical_url,
        description=description,
        author=author,
        site_name=site_name,
        opengraph=opengraph,
        twitter=twitter,
        meta_tags=meta_tags,
        json_ld=json_ld_blocks,
    )
