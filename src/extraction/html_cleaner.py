"""HTML cleaning and boilerplate removal for pipeline documents.

Deterministic, LLM-free extraction of clean textual content from raw HTML,
preventing 413 (Payload Too Large) errors and removing boilerplate elements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from bs4 import BeautifulSoup, Comment, FeatureNotFound, Tag

# Elements that contain non-content boilerplate, scripts, or display artifacts
BOILERPLATE_TAGS: Final[set[str]] = {
    "script",
    "style",
    "noscript",
    "iframe",
    "noembed",
    "svg",
    "canvas",
    "nav",
    "footer",
    "header",
    "aside",
    "form",
    "button",
    "dialog",
    "menu",
    "audio",
    "video",
    "select",
    "input",
    "textarea",
}

WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"[ \t]+")
MULTIPLE_NEWLINES_RE: Final[re.Pattern[str]] = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class CleanedDocument:
    """Representation of cleaned text and structural metrics from an HTML document."""

    clean_text: str
    source_url: str | None = None
    character_count: int = 0
    word_count: int = 0
    token_estimate: int = 0

    @property
    def html(self) -> str:
        """Alias for clean_text to maintain backward compatibility with pipeline expectations."""
        return self.clean_text


def estimate_tokens(text: str) -> int:
    """Estimate token count deterministically.

    Uses a conservative heuristic for English text (~4 characters or ~1.33 tokens per word)
    to prevent underestimating payload sizes before sending chunks to LLMs.
    """
    if not text:
        return 0
    words = len(text.split())
    if words == 0:
        return 0
    char_est = len(text) // 4
    word_est = int(words * 1.33)
    return max(char_est, word_est, 1)


def clean_html(html: str, *, source_url: str | None = None) -> CleanedDocument:
    """Safely parse HTML and extract clean, readable text without boilerplate.

    - Safely handles malformed, partial, or empty HTML.
    - Strips scripts, styles, navigation, headers, footers, and non-content elements.
    - Preserves logical paragraph and block boundaries.
    - Computes character count, word count, and token estimate.
    - Preserves provenance (source_url).

    Args:
        html: Raw HTML string.
        source_url: Optional origin URL of the document.

    Returns:
        CleanedDocument containing clean text and sizing metrics.
    """
    if not html or not html.strip():
        return CleanedDocument(
            clean_text="",
            source_url=source_url,
            character_count=0,
            word_count=0,
            token_estimate=0,
        )

    try:
        soup = BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        soup = BeautifulSoup(html, "html.parser")

    # 1. Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # 2. Decompose known boilerplate tags
    for tag in soup.find_all(BOILERPLATE_TAGS):
        tag.decompose()

    # 3. Decompose elements with navigation/banner/footer accessibility roles
    for tag in soup.find_all(attrs={"role": ["navigation", "banner", "contentinfo"]}):
        tag.decompose()

    # 4. Decompose aria-hidden elements
    for tag in soup.find_all(attrs={"aria-hidden": "true"}):
        tag.decompose()

    # 5. Locate core content container if present (<main>, <article>, role="main")
    main_candidate = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
    )

    target_element: Tag | BeautifulSoup
    if isinstance(main_candidate, Tag) and len(main_candidate.get_text(strip=True)) >= 40:
        target_element = main_candidate
    else:
        target_element = soup.body if soup.body is not None else soup

    # 6. Extract text with paragraph-level double newline separator
    extracted_text = target_element.get_text(separator="\n\n", strip=True)

    # 7. Normalize line whitespace while preserving paragraph breaks
    normalized_lines: list[str] = []
    for raw_line in extracted_text.splitlines():
        line = WHITESPACE_RE.sub(" ", raw_line).strip()
        normalized_lines.append(line)

    joined_text = "\n".join(normalized_lines)
    clean_text = MULTIPLE_NEWLINES_RE.sub("\n\n", joined_text).strip()

    char_count = len(clean_text)
    word_count = len(clean_text.split()) if clean_text else 0
    token_est = estimate_tokens(clean_text)

    return CleanedDocument(
        clean_text=clean_text,
        source_url=source_url,
        character_count=char_count,
        word_count=word_count,
        token_estimate=token_est,
    )
