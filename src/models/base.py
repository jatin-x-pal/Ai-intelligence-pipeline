"""Shared base models and validation helpers for canonical schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_timezone_aware(dt: datetime | str | None) -> datetime | None:
    """Validate that a datetime instance is timezone-aware.
    Accepts a datetime object or an ISO‑8601 string.
    Returns a timezone‑aware datetime or raises ValueError.
    """
    if dt is None:
        return None
    # If a string is provided, attempt to parse it
    if isinstance(dt, str):
        # Support ISO format with trailing Z (UTC) by converting to +00:00
        iso_str = dt.rstrip('Z') + '+00:00' if dt.endswith('Z') else dt
        try:
            parsed = datetime.fromisoformat(iso_str)
        except Exception as e:
            raise ValueError(f"Invalid datetime string: {dt}") from e
        dt = parsed
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("Datetime must be timezone-aware (e.g. UTC)")
    return dt


def validate_http_url(url: str | None) -> str | None:
    """Validate that a URL is a non-empty string starting with http:// or https://."""
    if url is None:
        return None
    if not isinstance(url, str):
        raise TypeError("URL must be a string")
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("URL cannot be empty")
    if not cleaned.startswith(("http://", "https://")):
        raise ValueError(f"URL must start with http:// or https://: {cleaned}")
    return cleaned


class SourceInfo(BaseModel):
    """Provenance information tracking the source name and URL of ingested records."""

    model_config = ConfigDict(frozen=False)

    name: str = Field(..., min_length=1, description="Name of the source site")
    url: str = Field(..., min_length=1, description="Original source URL")

    @field_validator("name")
    @classmethod
    def validate_source_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Source name cannot be blank")
        return cleaned

    @field_validator("url")
    @classmethod
    def validate_source_url(cls, v: Any) -> str:
        validated = validate_http_url(str(v))
        if validated is None:
            raise ValueError("Source URL cannot be empty")
        return validated
