"""Canonical Pydantic schema for News entity."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.models.base import SourceInfo, validate_http_url, validate_timezone_aware


class NewsContent(BaseModel):
    """Core content for news article records."""

    title: str = Field(
        ...,
        min_length=1,
        description="Title of the news article",
    )
    article_url: str = Field(
        ...,
        description="Original article URL",
    )
    published_date: datetime = Field(
        ...,
        description="Timezone-aware ISO-8601 publication date",
    )
    text: str = Field(
        ...,
        min_length=1,
        description="Full text content of the article",
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Title cannot be blank")
        return cleaned

    @field_validator("article_url")
    @classmethod
    def validate_article_url(cls, v: str) -> str:
        validated = validate_http_url(v)
        if validated is None:
            raise ValueError("article_url cannot be empty")
        return validated

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Article text cannot be blank")
        return cleaned

    @field_validator("published_date")
    @classmethod
    def validate_published_date(cls, v: datetime) -> datetime:
        validated = validate_timezone_aware(v)
        if validated is None:
            raise ValueError("published_date cannot be null")
        return validated


class News(BaseModel):
    """Canonical news entity model."""

    schemaVersion: str = Field(
        default="1.0",
        description="Versioning for the schema (e.g., '1.0')",
    )
    recordType: Literal["NEWS"] = Field(
        default="NEWS",
        description="Fixed to 'NEWS'",
    )
    source: SourceInfo = Field(
        ...,
        description="Source site name and original URL",
    )
    content: NewsContent = Field(
        ...,
        description="News payload containing title, article_url, published_date, and text",
    )
    collectedAt: datetime = Field(
        ...,
        description="Timezone-aware ISO-8601 collection timestamp",
    )

    @field_validator("collectedAt")
    @classmethod
    def validate_collected_at(cls, v: datetime) -> datetime:
        validated = validate_timezone_aware(v)
        if validated is None:
            raise ValueError("collectedAt cannot be null")
        return validated
