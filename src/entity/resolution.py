"""Deterministic entity resolution utilities.

The public entry point is :func:`resolve_entity` which returns an
:class:`~src.entity.models.EntityMappingLog` describing how the raw name was
mapped to a canonical name.
"""

from __future__ import annotations

import re

from .aliases import ALIAS_MAP
from .models import EntityMappingLog
from .seed_startups import SEED_STARTUPS

# Known corporate suffixes (case‑insensitive, punctuation optional)
_SUFFIXES = [
    "inc",
    "inc.",
    "llc",
    "ltd",
    "limited",
    "corp",
    "corporation",
]

def _collapse_whitespace(name: str) -> str:
    """Replace any run of whitespace characters with a single space."""
    return re.sub(r"\s+", " ", name.strip())

def _remove_punctuation(name: str) -> str:
    """Remove commas and periods which are safe to discard for matching."""
    return re.sub(r"[.,]", "", name)

def _strip_suffix(name: str) -> str:
    """Remove a trailing corporate suffix if present.

    The suffix list includes common variations. Matching is case‑insensitive
    and ignores trailing punctuation or commas.
    """
    parts = name.split()
    if not parts:
        return name
    last = parts[-1].lower().rstrip('.,')
    if last in _SUFFIXES:
        return " ".join(parts[:-1])
    return name

def _normalize(name: str) -> str:
    """Return a deterministic normalized representation of *name*.

    Steps (in order):
    1. Trim and collapse whitespace.
    2. Remove safe punctuation (commas, periods).
    3. Strip corporate suffix.
    4. Lower‑case for case‑insensitive comparison.
    """
    name = _collapse_whitespace(name)
    name = _remove_punctuation(name)
    # Do NOT strip corporate suffixes here; they are handled via explicit alias mapping.
    return name.lower()

# Pre‑compute normalized look‑ups for seed list and alias map for efficiency
_NORMALIZED_SEED = { _normalize(canonical): canonical for canonical in SEED_STARTUPS }
_NORMALIZED_ALIAS_KEYS = { _normalize(alias): alias for alias in ALIAS_MAP }

def resolve_entity(raw_name: str, source: str | None = None) -> EntityMappingLog:
    """Resolve *raw_name* to a deterministic canonical entity name.

    Parameters
    ----------
    raw_name: str
        The name extracted from a source document.
    source: Optional[str]
        Optional provenance identifier (e.g., URL or source name).

    Returns
    -------
    EntityMappingLog
        A log entry containing the raw name, the resolved canonical name (or
        ``None`` when unresolved), the matching reason, and provenance.
    """
    # 1. Exact canonical match against seed list (case‑sensitive)
    if raw_name in SEED_STARTUPS:
        return EntityMappingLog(
            raw_name=raw_name,
            canonical_name=raw_name,
            match_reason="exact_canonical",
            source=source,
        )

    # 2. Exact alias map match (case‑sensitive)
    if raw_name in ALIAS_MAP:
        return EntityMappingLog(
            raw_name=raw_name,
            canonical_name=ALIAS_MAP[raw_name],
            match_reason="alias",
            source=source,
        )

    # Normalized form for subsequent rules
    norm = _normalize(raw_name)

    # 3. Normalized match against seed list
    if norm in _NORMALIZED_SEED:
        return EntityMappingLog(
            raw_name=raw_name,
            canonical_name=_NORMALIZED_SEED[norm],
            match_reason="normalized_canonical",
            source=source,
        )

    # 4. Normalized match against alias keys
    if norm in _NORMALIZED_ALIAS_KEYS:
        alias_key = _NORMALIZED_ALIAS_KEYS[norm]
        return EntityMappingLog(
            raw_name=raw_name,
            canonical_name=ALIAS_MAP[alias_key],
            match_reason="alias",
            source=source,
        )

    # 5. Unresolved
    return EntityMappingLog(
        raw_name=raw_name,
        canonical_name=None,
        match_reason="unresolved",
        source=source,
    )
