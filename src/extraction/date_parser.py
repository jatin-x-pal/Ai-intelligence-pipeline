import json
import re
from datetime import UTC, datetime, timedelta

from bs4 import BeautifulSoup, FeatureNotFound

# Helper functions

def _make_aware(dt: datetime) -> datetime:
    """Convert datetime to timezone-aware UTC.
    Naive datetimes are assumed to be UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_iso(date_str: str) -> datetime | None:
    """Parse ISO/RFC date strings using fromisoformat, handling trailing 'Z'."""
    try:
        # Replace Z with +00:00 for fromisoformat compatibility
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        dt = datetime.fromisoformat(date_str)
        return _make_aware(dt)
    except ValueError:
        return None

# Extraction functions

def extract_date_from_jsonld(soup: BeautifulSoup) -> datetime | None:
    """Search for <script type="application/ld+json"> blocks and extract a date.
    Looks for common fields: datePublished, uploadDate, dateCreated, dateModified.
    """
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
        except (json.JSONDecodeError, TypeError):
            continue
        # JSON-LD can be a dict or list of dicts
        items = data if isinstance(data, list) else [data]
        for item in items:
            for key in ("datePublished", "uploadDate", "dateCreated", "dateModified"):
                val = item.get(key)
                if isinstance(val, str):
                    dt = _parse_iso(val)
                    if dt:
                        return dt
    return None


def extract_date_from_meta(soup: BeautifulSoup) -> datetime | None:
    """Extract date from OpenGraph or generic meta tags.
    Prioritises "article:published_time" and "og:published_time".
    Also checks meta[name="pubdate"] and meta[name="date"].
    """
    meta_selectors = [
        ("property", "article:published_time"),
        ("property", "og:published_time"),
        ("name", "pubdate"),
        ("name", "date"),
        ("name", "publication_date"),
    ]
    for attr, value in meta_selectors:
        tag = soup.find('meta', attrs={attr: value})
        if tag and tag.get('content'):
            dt = _parse_iso(tag['content'])
            if dt:
                return dt
    return None


def extract_date_from_time(soup: BeautifulSoup) -> datetime | None:
    """Extract date from <time> elements.
    Prefer the datetime attribute, fallback to the element text.
    """
    for time_tag in soup.find_all('time'):
        dt_str = time_tag.get('datetime') or time_tag.get_text(strip=True)
        if dt_str:
            dt = _parse_iso(dt_str)
            if dt:
                return dt
    return None


def extract_date_from_visible_text(soup: BeautifulSoup) -> datetime | None:
    """Search visible text for an ISO‑like date pattern.
    This is a simple heuristic and may return None.
    """
    text = soup.get_text(separator=' ', strip=True)
    # Look for patterns like 2026-09-09T10:00:00+02:00 or 2026-09-09 10:00
    iso_regex = r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[\+\-]\d{2}:?\d{2})?"
    match = re.search(iso_regex, text)
    if match:
        dt = _parse_iso(match.group(0))
        if dt:
            return dt
    return None

# Relative date handling
_relative_regex = re.compile(
    r"(?P<value>\d+)\s+(?P<unit>seconds?|minutes?|hours?|days?)\s+ago",
    re.IGNORECASE,
)

def parse_relative_date(text: str, reference: datetime) -> datetime | None:
    """Parse simple relative expressions like "2 hours ago" or "yesterday".
    Returns a timezone‑aware UTC datetime.
    """
    text = text.strip().lower()
    if text == "yesterday":
        dt = reference - timedelta(days=1)
        return _make_aware(dt)
    m = _relative_regex.search(text)
    if m:
        value = int(m.group('value'))
        unit = m.group('unit').lower()
        delta = None
        if unit.startswith('second'):
            delta = timedelta(seconds=value)
        elif unit.startswith('minute'):
            delta = timedelta(minutes=value)
        elif unit.startswith('hour'):
            delta = timedelta(hours=value)
        elif unit.startswith('day'):
            delta = timedelta(days=value)
        if delta:
            dt = reference - delta
            return _make_aware(dt)
    return None

# Public API

def parse_publication_date(html: str, reference: datetime | None = None) -> datetime | None:
    """Extract and normalise a publication date from raw HTML.
    Extraction priority:
    1. JSON‑LD
    2. OpenGraph / meta tags
    3. <time> elements
    4. Visible ISO‑like text
    5. Relative expressions found in visible text
    Returns a UTC aware ``datetime`` or ``None`` if no reliable date is found.
    """
    if reference is None:
        reference = datetime.now(UTC)
    try:
        soup = BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        soup = BeautifulSoup(html, "html.parser")

    for extractor in (
        extract_date_from_jsonld,
        extract_date_from_meta,
        extract_date_from_time,
        extract_date_from_visible_text,
    ):
        dt = extractor(soup)
        if dt:
            return dt

    # Fallback: look for relative expressions in the whole text
    rel_dt = parse_relative_date(soup.get_text(separator=' ', strip=True), reference)
    if rel_dt:
        return rel_dt
    return None

def is_fresh(publication_dt: datetime | None, reference: datetime | None = None, max_age: timedelta = timedelta(hours=24)) -> bool:
    """Return ``True`` if ``publication_dt`` is within ``max_age`` of ``reference``.
    ``publication_dt`` must be a timezone‑aware UTC datetime; ``None`` is treated as not fresh.
    """
    if publication_dt is None:
        return False
    if reference is None:
        reference = datetime.now(UTC)
    # Ensure both are UTC aware
    pub = publication_dt.astimezone(UTC)
    ref = reference.astimezone(UTC)
    return (ref - pub) <= max_age
