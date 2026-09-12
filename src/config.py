"""Pipeline configuration loaded from environment variables.

Uses pydantic-settings to validate and type-check all configuration at startup.
Never hardcodes secrets — every sensitive value comes from the environment.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseModel as BaseSettings


class PostgresSettings(BaseSettings):
    """PostgreSQL connection parameters."""

    model_config = ConfigDict(env_prefix="POSTGRES_")

    host: str = "localhost"
    port: int = 5432
    db: str = "ai_pipeline"
    user: str = "pipeline"
    password: str = "changeme_in_production"

    @property
    def dsn(self) -> str:
        """asyncpg-compatible DSN."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class RedisSettings(BaseSettings):
    """Redis connection parameters."""

    model_config = ConfigDict(env_prefix="REDIS_")

    host: str = "localhost"
    port: int = 6379
    db: int = 0

    @property
    def url(self) -> str:
        """redis-py compatible URL."""
        return f"redis://{self.host}:{self.port}/{self.db}"


class ConcurrencySettings(BaseSettings):
    """Concurrency limits for pipeline stages."""

    max_concurrent_http: int = Field(default=50, ge=1)
    max_concurrent_playwright: int = Field(default=5, ge=1)
    max_concurrent_llm: int = Field(default=10, ge=1)


class Settings(BaseSettings):
    """Root application settings.

    Loads from .env file and environment variables.
    Environment variables take precedence over .env values.
    """

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"

    # LLM configuration
    llm_primary_provider: str = "gemini"
    llm_fallback_provider: str = "groq"
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    # Google Sheets configuration
    GOOGLE_SHEETS_SPREADSHEET_ID: str | None = None
    GOOGLE_SHEETS_CREDENTIALS_FILE: str | None = None


    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    concurrency: ConcurrencySettings = Field(default_factory=ConcurrencySettings)


def get_settings() -> Settings:
    """Create and return validated settings.

    Call once at application startup and pass the instance via
    dependency injection — do not call repeatedly.
    """
    return Settings()
