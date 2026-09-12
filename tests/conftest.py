"""Shared test fixtures and configuration."""

from __future__ import annotations

import sys
from pathlib import Path

# Add the project root (parent of the 'src' package) to sys.path for imports in tests
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

import pytest

from src.config import ConcurrencySettings, PostgresSettings, RedisSettings, Settings


@pytest.fixture
def postgres_settings() -> PostgresSettings:
    """Default PostgreSQL settings for tests."""
    return PostgresSettings(
        host="localhost",
        port=5432,
        db="ai_pipeline",
        user="pipeline",
        password="changeme_in_production",
    )


@pytest.fixture
def redis_settings() -> RedisSettings:
    """Default Redis settings for tests."""
    return RedisSettings(host="localhost", port=6379, db=0)


@pytest.fixture
def settings(
    postgres_settings: PostgresSettings,
    redis_settings: RedisSettings,
) -> Settings:
    """Full application settings for tests."""
    return Settings(
        log_level="DEBUG",
        postgres=postgres_settings,
        redis=redis_settings,
        concurrency=ConcurrencySettings(),
    )
