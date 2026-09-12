"""Utilities for crawling helpers.

This module currently provides a simple function to detect anti‑bot block pages
based on common keywords. It is used by both the HTTP and Browser crawlers to
centralise the logic and make future extensions (e.g., additional patterns) easy.
"""

def _detect_block_page(content: str) -> bool:
    """Return ``True`` if *content* appears to be an anti‑bot block page.

    The detection is case‑insensitive and checks for a set of keywords that are
    typical for CAPTCHAs or access‑challenge pages. The list can be extended in a
    deterministic manner without affecting existing behaviour.
    """
    lowered = content.lower()
    keywords = (
        "captcha",
        "access denied",
        "blocked",
        "challenge",
        "verify you are human",
        "recaptcha",
    )
    return any(k in lowered for k in keywords)
