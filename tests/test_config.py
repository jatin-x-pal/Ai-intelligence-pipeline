"""Tests for configuration loading and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import ConcurrencySettings, PostgresSettings, RedisSettings, Settings


class TestPostgresSettings:
    """Test PostgreSQL configuration."""

    def test_default_values(self) -> None:
        settings = PostgresSettings()
        assert settings.host == "localhost"
        assert settings.port == 5432
        assert settings.db == "ai_pipeline"
        assert settings.user == "pipeline"

    def test_dsn_format(self) -> None:
        settings = PostgresSettings(
            host="db.example.com",
            port=5433,
            db="testdb",
            user="testuser",
            password="testpass",
        )
        assert settings.dsn == "postgresql://testuser:testpass@db.example.com:5433/testdb"

    def test_dsn_default(self, postgres_settings: PostgresSettings) -> None:
        dsn = postgres_settings.dsn
        assert dsn.startswith("postgresql://")
        assert "pipeline" in dsn
        assert "5432" in dsn


class TestRedisSettings:
    """Test Redis configuration."""

    def test_default_values(self) -> None:
        settings = RedisSettings()
        assert settings.host == "localhost"
        assert settings.port == 6379
        assert settings.db == 0

    def test_url_format(self) -> None:
        settings = RedisSettings(host="cache.example.com", port=6380, db=2)
        assert settings.url == "redis://cache.example.com:6380/2"


class TestConcurrencySettings:
    """Test concurrency limit configuration."""

    def test_default_values(self) -> None:
        settings = ConcurrencySettings()
        assert settings.max_concurrent_http == 50
        assert settings.max_concurrent_playwright == 5
        assert settings.max_concurrent_llm == 10

    def test_rejects_zero_concurrency(self) -> None:
        with pytest.raises(ValidationError):
            ConcurrencySettings(max_concurrent_http=0)

    def test_rejects_negative_concurrency(self) -> None:
        with pytest.raises(ValidationError):
            ConcurrencySettings(max_concurrent_playwright=-1)


class TestSettings:
    """Test root application settings."""

    def test_default_log_level(self) -> None:
        settings = Settings()
        assert settings.log_level == "INFO"

    def test_nested_postgres(self) -> None:
        settings = Settings()
        assert isinstance(settings.postgres, PostgresSettings)
        assert settings.postgres.host == "localhost"

    def test_nested_redis(self) -> None:
        settings = Settings()
        assert isinstance(settings.redis, RedisSettings)
        assert settings.redis.port == 6379

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        settings = Settings()
        assert settings.log_level == "DEBUG"
