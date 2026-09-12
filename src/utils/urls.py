"""Deterministic URL normalization and deduplication key generation.

Provides robust URL canonicalization:
- Scheme and host lowercasing
- Fragment removal
- Default port stripping (80 for http, 443 for https)
- Tracking parameter stripping (utm_*, fbclid, gclid, etc.)
- Deterministic query parameter sorting
- Safe path normalization
- SHA-256 deduplication key computation
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from typing import Final
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Known tracking parameter names (case-insensitive)
TRACKING_PARAMS: Final[set[str]] = {
    # Google Analytics / Urchin
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_reader",
    "utm_referrer",
    "utm_name",
    # Meta / Facebook / Instagram
    "fbclid",
    "igshid",
    # Google Ads
    "gclid",
    "gclsrc",
    "dclid",
    "wbraid",
    "gbraid",
    # Microsoft / Bing
    "msclkid",
    # Twitter / X
    "twclid",
    # Mailchimp & Email trackers
    "mc_cid",
    "mc_eid",
    # Analytics / Affiliates
    "yclid",
    "_openstat",
    "ref_src",
    "ref_url",
}

SUPPORTED_SCHEMES: Final[set[str]] = {"http", "https"}
CONSECUTIVE_SLASHES_RE: Final[re.Pattern[str]] = re.compile(r"/{2,}")


def is_tracking_param(param_name: str) -> bool:
    """Check if a query parameter is a known tracking or marketing parameter."""
    lower_name = param_name.strip().lower()
    if lower_name.startswith("utm_"):
        return True
    return lower_name in TRACKING_PARAMS


def is_valid_url(url: str | None) -> bool:
    """Validate that a URL has a supported HTTP/HTTPS scheme and non-empty host."""
    if not isinstance(url, str):
        return False
    stripped = url.strip()
    if not stripped:
        return False
    try:
        parts = urlsplit(stripped)
        return parts.scheme.lower() in SUPPORTED_SCHEMES and bool(parts.netloc)
    except Exception:  # noqa: BLE001  # Preserve original behavior but specify exception type from urllib.error
        return False
        return False


def normalize_url(url: str) -> str:
    """Normalize a URL to its canonical form deterministically.

    Steps:
    1. Validate scheme (http or https) and presence of hostname.
    2. Lowercase scheme and hostname.
    3. Strip default ports (80 for http, 443 for https).
    4. Remove URL fragments (#...).
    5. Strip tracking and analytics query parameters.
    6. Sort remaining query parameters deterministically.
    7. Normalize path dot-segments while preserving directory trailing slash.

    Args:
        url: Raw URL string.

    Returns:
        Canonical, normalized URL string.

    Raises:
        ValueError: If the URL is empty, malformed, or has an unsupported scheme.
    """
    if not is_valid_url(url):
        raise ValueError(f"Invalid or unsupported URL: {url!r}")

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()

    # Normalize netloc and strip default ports
    netloc = parts.netloc.lower()
    if ":" in netloc:
        user_info = ""
        host_port = netloc
        if "@" in netloc:
            user_info, host_port = netloc.split("@", 1)
            user_info += "@"

        if ":" in host_port:
            host, port_str = host_port.split(":", 1)
            if (scheme == "http" and port_str == "80") or (scheme == "https" and port_str == "443"):
                netloc = f"{user_info}{host}"
            else:
                netloc = f"{user_info}{host}:{port_str}"

    # Normalize path
    raw_path = parts.path or "/"
    has_trailing_slash = raw_path.endswith("/")
    # Clean multiple consecutive slashes
    clean_path = CONSECUTIVE_SLASHES_RE.sub("/", raw_path)
    normalized_path = posixpath.normpath(clean_path)
    if has_trailing_slash and not normalized_path.endswith("/"):
        normalized_path += "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"

    # Filter and sort query parameters
    filtered_query = ""
    if parts.query:
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        meaningful_pairs = [
            (k, v) for k, v in pairs if not is_tracking_param(k)
        ]
        meaningful_pairs.sort(key=lambda item: (item[0], item[1]))
        if meaningful_pairs:
            filtered_query = urlencode(meaningful_pairs)

    # Fragments are strictly omitted in canonical URLs
    return urlunsplit((scheme, netloc, normalized_path, filtered_query, ""))


def compute_dedup_key(url: str) -> str:
    """Generate a deterministic 64-character SHA-256 key from a URL.

    Normalizes the URL first, ensuring that equivalent URLs produce
    identical deduplication keys.

    Args:
        url: Raw or normalized URL.

    Returns:
        Hex-encoded SHA-256 digest string.

    Raises:
        ValueError: If the URL is invalid.
    """
    canonical = normalize_url(url)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
