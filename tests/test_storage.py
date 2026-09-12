"""Tests for storage layer — database and Redis.

Tests marked with @pytest.mark.integration require running services.
Unit tests use mocks and verify interface behavior without live connections.
"""

from __future__ import annotations

import pytest

from src.config import PostgresSettings, RedisSettings
from src.storage.database import DatabasePool
from src.storage.redis_client import RedisClient


class TestDatabasePoolUnit:
    """Unit tests for DatabasePool (no live connection required)."""

    def test_pool_not_connected_raises(self, postgres_settings: PostgresSettings) -> None:
        db = DatabasePool(postgres_settings)
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.pool

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(
        self, postgres_settings: PostgresSettings
    ) -> None:
        db = DatabasePool(postgres_settings)
        # Should not raise
        await db.disconnect()


class TestRedisClientUnit:
    """Unit tests for RedisClient (no live connection required)."""

    def test_client_not_connected_raises(self, redis_settings: RedisSettings) -> None:
        client = RedisClient(redis_settings)
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.client

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(
        self, redis_settings: RedisSettings
    ) -> None:
        client = RedisClient(redis_settings)
        # Should not raise
        await client.disconnect()


class TestDatabasePoolIntegration:
    """Integration tests — require a running PostgreSQL instance."""

    pytestmark = pytest.mark.integration

    @pytest.mark.asyncio
    async def test_connect_and_health_check(
        self, postgres_settings: PostgresSettings
    ) -> None:
        db = DatabasePool(postgres_settings)
        try:
            await db.connect(min_size=1, max_size=2)
            assert await db.health_check() is True
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_fetchval(self, postgres_settings: PostgresSettings) -> None:
        db = DatabasePool(postgres_settings)
        try:
            await db.connect(min_size=1, max_size=2)
            result = await db.fetchval("SELECT 42")
            assert result == 42
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_fetch(self, postgres_settings: PostgresSettings) -> None:
        db = DatabasePool(postgres_settings)
        try:
            await db.connect(min_size=1, max_size=2)
            rows = await db.fetch("SELECT 1 AS a, 2 AS b")
            assert len(rows) == 1
            assert rows[0]["a"] == 1
            assert rows[0]["b"] == 2
        finally:
            await db.disconnect()

    @pytest.mark.asyncio
    async def test_double_connect_warns(
        self, postgres_settings: PostgresSettings
    ) -> None:
        db = DatabasePool(postgres_settings)
        try:
            await db.connect(min_size=1, max_size=2)
            # Second connect should warn but not error
            await db.connect(min_size=1, max_size=2)
            assert await db.health_check() is True
        finally:
            await db.disconnect()


class TestRedisClientIntegration:
    """Integration tests — require a running Redis instance."""

    pytestmark = pytest.mark.integration

    @pytest.mark.asyncio
    async def test_connect_and_health_check(
        self, redis_settings: RedisSettings
    ) -> None:
        client = RedisClient(redis_settings)
        try:
            await client.connect()
            assert await client.health_check() is True
        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_double_connect_warns(
        self, redis_settings: RedisSettings
    ) -> None:
        client = RedisClient(redis_settings)
        try:
            await client.connect()
            # Second connect should warn but not error
            await client.connect()
            assert await client.health_check() is True
        finally:
            await client.disconnect()
