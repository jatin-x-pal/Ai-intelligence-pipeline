"""Startup extraction utilities.

Provides deterministic parsing of startup detail pages to construct ``Startup`` model data.
"""

import re

from bs4 import BeautifulSoup

from src.utils.logging import get_logger

logger = get_logger(__name__)

def extract_entity_name(soup: BeautifulSoup) -> str:
    """Extract the canonical startup name.

    Heuristic: use the first <h1> tag text, stripped. If not found, fall back to the
    <title> tag.
    """
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    raise ValueError("Unable to locate startup name")


def extract_employee_count(soup: BeautifulSoup) -> int | None:
    """Extract employee count if present.

    Looks for patterns like "Employees: 42" or "42 employees" in the page text.
    Returns ``None`` when not found or when parsing fails.
    """
    text = soup.get_text(separator=" ")
    match = re.search(r"(?i)employees?\s*[:]?\s*(\d+)", text)
    if not match:
        match = re.search(r"(\d+)\s*employees?", text, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def build_startup_content(html: str) -> dict:
    """Parse ``html`` and return a dict suitable for ``StartupContent`` construction.

    Returns a mapping with keys ``entityName`` and ``data`` containing ``employeeCount``.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:
        # Log parsing error for debugging
        logger.exception("html_parse_error", exception=exc)
        soup = BeautifulSoup(html, "html.parser")
    entity_name = extract_entity_name(soup)
    employee_count = extract_employee_count(soup)
    return {
        "entityName": entity_name,
        "data": {"employeeCount": employee_count},
    }
