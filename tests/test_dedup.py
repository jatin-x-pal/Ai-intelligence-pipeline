"""Tests for URL normalization, deduplication keys, and deduplicator storage."""

from __future__ import annotations

import asyncio

import pytest

from src.storage.dedup import InMemoryDeduplicator
from src.utils.urls import (
    compute_dedup_key,
    is_tracking_param,
    is_valid_url,
    normalize_url,
)


class TestUrlValidation:
    """Tests for is_valid_url helper."""

    def test_valid_http_and_https_urls(self) -> None:
        assert is_valid_url("http://example.com") is True
        assert is_valid_url("https://example.com/path?q=1") is True
        assert is_valid_url("HTTPS://SUB.EXAMPLE.ORG:8080") is True

    def test_invalid_urls(self) -> None:
        assert is_valid_url("") is False
        assert is_valid_url("   ") is False
        assert is_valid_url(None) is False
        assert is_valid_url("ftp://example.com") is False
        assert is_valid_url("javascript:alert(1)") is False
        assert is_valid_url("mailto:test@example.com") is False
        assert is_valid_url("relative/path/only") is False


class TestTrackingParamDetection:
    """Tests for tracking parameter identification."""

    def test_utm_parameters(self) -> None:
        assert is_tracking_param("utm_source") is True
        assert is_tracking_param("utm_campaign") is True
        assert is_tracking_param("UTM_MEDIUM") is True
        assert is_tracking_param("utm_custom_tag") is True

    def test_ad_and_platform_click_ids(self) -> None:
        assert is_tracking_param("fbclid") is True
        assert is_tracking_param("gclid") is True
        assert is_tracking_param("msclkid") is True
        assert is_tracking_param("twclid") is True
        assert is_tracking_param("mc_eid") is True

    def test_meaningful_parameters_not_flagged(self) -> None:
        assert is_tracking_param("id") is False
        assert is_tracking_param("page") is False
        assert is_tracking_param("q") is False
        assert is_tracking_param("search") is False
        assert is_tracking_param("category") is False


class TestUrlNormalization:
    """Tests for canonical URL normalization."""

    def test_scheme_and_hostname_lowercased(self) -> None:
        url = "HTTPS://WWW.EXAMPLE.COM/Article/Path"
        expected = "https://www.example.com/Article/Path"
        assert normalize_url(url) == expected

    def test_default_ports_stripped(self) -> None:
        assert normalize_url("http://example.com:80/path") == "http://example.com/path"
        assert normalize_url("https://example.com:443/path") == "https://example.com/path"

    def test_custom_ports_preserved(self) -> None:
        assert normalize_url("http://example.com:8080/path") == "http://example.com:8080/path"
        assert normalize_url("https://example.com:8443/path") == "https://example.com:8443/path"

    def test_root_path_normalized_to_slash(self) -> None:
        assert normalize_url("https://example.com") == "https://example.com/"
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_fragments_removed(self) -> None:
        assert normalize_url("https://example.com/post#comments") == "https://example.com/post"
        assert normalize_url("https://example.com/#top") == "https://example.com/"

    def test_tracking_parameters_removed(self) -> None:
        url = "https://example.com/item?id=42&utm_source=twitter&utm_medium=social&fbclid=abc"
        expected = "https://example.com/item?id=42"
        assert normalize_url(url) == expected

    def test_all_tracking_params_leaves_clean_url(self) -> None:
        url = "https://example.com/item?utm_source=newsletter&utm_campaign=fall"
        expected = "https://example.com/item"
        assert normalize_url(url) == expected

    def test_meaningful_query_params_sorted_deterministically(self) -> None:
        url1 = "https://example.com/search?sort=desc&page=2&q=ai"
        url2 = "https://example.com/search?q=ai&sort=desc&page=2"
        assert normalize_url(url1) == "https://example.com/search?page=2&q=ai&sort=desc"
        assert normalize_url(url1) == normalize_url(url2)

    def test_path_redundant_slashes_cleaned(self) -> None:
        url = "https://example.com//docs///api//v1/"
        assert normalize_url(url) == "https://example.com/docs/api/v1/"

    def test_path_dot_segments_resolved(self) -> None:
        url = "https://example.com/a/b/../c"
        assert normalize_url(url) == "https://example.com/a/c"

    def test_invalid_urls_raise_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid or unsupported URL"):
            normalize_url("")

        with pytest.raises(ValueError, match="Invalid or unsupported URL"):
            normalize_url("ftp://example.com/file")

        with pytest.raises(ValueError, match="Invalid or unsupported URL"):
            normalize_url("just-a-string")

    def test_distinct_urls_never_merged(self) -> None:
        # Different paths
        assert normalize_url("https://example.com/item-a") != normalize_url("https://example.com/item-b")
        # Different hosts
        assert normalize_url("https://sub1.example.com/") != normalize_url("https://sub2.example.com/")
        # Different protocols
        assert normalize_url("http://example.com/a") != normalize_url("https://example.com/a")
        # Different meaningful query values
        assert normalize_url("https://example.com/?page=1") != normalize_url("https://example.com/?page=2")
        # File vs directory
        assert normalize_url("https://example.com/item") != normalize_url("https://example.com/item/")


class TestComputeDedupKey:
    """Tests for deterministic SHA-256 deduplication keys."""

    def test_valid_sha256_format(self) -> None:
        key = compute_dedup_key("https://example.com/test")
        assert isinstance(key, str)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_equivalent_urls_produce_same_key(self) -> None:
        url1 = "HTTP://EXAMPLE.COM:80/news?category=ai&utm_source=feed#headline"
        url2 = "http://example.com/news?utm_medium=rss&category=ai"
        assert compute_dedup_key(url1) == compute_dedup_key(url2)

    def test_distinct_urls_produce_different_keys(self) -> None:
        key1 = compute_dedup_key("https://example.com/doc1")
        key2 = compute_dedup_key("https://example.com/doc2")
        assert key1 != key2

    def test_invalid_url_raises_error(self) -> None:
        with pytest.raises(ValueError):
            compute_dedup_key("invalid_url")


class TestInMemoryDeduplicator:
    """Tests for the in-memory deduplication storage implementation."""

    @pytest.mark.asyncio
    async def test_initial_state(self) -> None:
        dedup = InMemoryDeduplicator()
        assert await dedup.count() == 0
        assert await dedup.is_seen("https://example.com") is False

    @pytest.mark.asyncio
    async def test_mark_seen_and_is_seen(self) -> None:
        dedup = InMemoryDeduplicator()
        url = "https://example.com/paper1"

        # First time seen
        assert await dedup.mark_seen(url) is True
        assert await dedup.is_seen(url) is True
        assert await dedup.count() == 1

        # Second time is duplicate
        assert await dedup.mark_seen(url) is False
        assert await dedup.count() == 1

    @pytest.mark.asyncio
    async def test_check_and_set_with_equivalent_urls(self) -> None:
        dedup = InMemoryDeduplicator()

        raw_url1 = "HTTPS://EXAMPLE.COM/article?tag=deeplearning&utm_source=twitter#top"
        raw_url2 = "https://example.com/article?utm_medium=social&tag=deeplearning"

        # First visit records entry
        assert await dedup.check_and_set(raw_url1) is True
        # Second visit with tracking params/casing variation is detected as duplicate
        assert await dedup.check_and_set(raw_url2) is False
        assert await dedup.is_seen(raw_url2) is True
        assert await dedup.count() == 1

    @pytest.mark.asyncio
    async def test_distinct_urls_accumulate(self) -> None:
        dedup = InMemoryDeduplicator()
        urls = [
            f"https://example.com/article/{i}" for i in range(10)
        ]

        for u in urls:
            assert await dedup.check_and_set(u) is True

        assert await dedup.count() == 10

        # Adding them again should all return False
        for u in urls:
            assert await dedup.check_and_set(u) is False

        assert await dedup.count() == 10

    @pytest.mark.asyncio
    async def test_clear(self) -> None:
        dedup = InMemoryDeduplicator()
        await dedup.mark_seen("https://example.com/1")
        await dedup.mark_seen("https://example.com/2")
        assert await dedup.count() == 2

        await dedup.clear()
        assert await dedup.count() == 0
        assert await dedup.is_seen("https://example.com/1") is False

    @pytest.mark.asyncio
    async def test_invalid_url_handling(self) -> None:
        dedup = InMemoryDeduplicator()
        assert await dedup.is_seen("not-a-url") is False
        with pytest.raises(ValueError):
            await dedup.mark_seen("not-a-url")

    @pytest.mark.asyncio
    async def test_concurrent_deduplication(self) -> None:
        dedup = InMemoryDeduplicator()
        url = "https://example.com/concurrency-test"

        # Fire 20 concurrent check_and_set tasks for the same URL
        tasks = [dedup.check_and_set(url) for _ in range(20)]
        results = await asyncio.gather(*tasks)

        # Exactly one task should have succeeded (returned True), the other 19 False
        assert results.count(True) == 1
        assert results.count(False) == 19
        assert await dedup.count() == 1
