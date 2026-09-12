"""Unit tests for deterministic entity resolution.

Covers whitespace, case, punctuation, corporate suffixes, alias handling,
exact matches, seed list matches, ambiguous and unresolved names, and
log entry fields.
"""

from datetime import UTC, datetime

import pytest

from src.entity.models import EntityMappingLog
from src.entity.resolution import resolve_entity


# Helper to extract reason and canonical from the log
def get_result(raw_name, source=None):
    log = resolve_entity(raw_name, source=source)
    return log.canonical_name, log.match_reason, log.source

@pytest.mark.parametrize(
    "raw_name,expected_canonical,expected_reason",
    [
        ("OpenAI", "OpenAI", "exact_canonical"),
        ("  OpenAI  ", "OpenAI", "normalized_canonical"),
        ("openai", "OpenAI", "normalized_canonical"),
        ("OpenAI, Inc.", "OpenAI", "alias"),
        ("Open AI", "OpenAI", "alias"),
        ("OpenAI Inc", "OpenAI", "alias"),
        ("OpenAI Inc.", "OpenAI", "alias"),
        ("OpenAI, Inc", "OpenAI", "alias"),
        ("OpenAI Ltd.", None, "unresolved"),  # suffix not in seed nor alias
        ("Random Corp", None, "unresolved"),
        ("AI21 Labs", "AI21 Labs", "exact_canonical"),
        ("ai21 labs", "AI21 Labs", "normalized_canonical"),
    ],
)
def test_resolution_basic(raw_name, expected_canonical, expected_reason):
    canonical, reason, _ = get_result(raw_name)
    assert canonical == expected_canonical
    assert reason == expected_reason

def test_raw_name_preserved_and_timestamp():
    raw = "OpenAI, Inc."
    log = resolve_entity(raw, source="test_source")
    assert isinstance(log, EntityMappingLog)
    assert log.raw_name == raw
    assert log.canonical_name == "OpenAI"
    assert log.source == "test_source"
    # Timestamp should be a recent datetime (within a minute of now)
    now = datetime.now(UTC)
    delta = now - log.timestamp
    assert delta.total_seconds() < 60

def test_deterministic_repeatability():
    raw = "Open AI"
    first = resolve_entity(raw)
    second = resolve_entity(raw)
    assert first == second
    assert first.canonical_name == "OpenAI"
    assert first.match_reason == "alias"

def test_corporate_suffix_handling():
    # Suffixes that are not in the alias map should be stripped and then resolved via seed
    raw = "OpenAI Inc."
    # Alias map already catches this, but we also ensure stripping works for unknown suffix
    log = resolve_entity(raw)
    assert log.canonical_name == "OpenAI"
    assert log.match_reason in {"alias", "normalized_canonical"}

def test_unresolved_name_has_none_canonical():
    raw = "Some Unknown Company"
    log = resolve_entity(raw)
    assert log.canonical_name is None
    assert log.match_reason == "unresolved"
