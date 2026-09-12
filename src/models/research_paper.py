"""Canonical Pydantic schema for Research Paper entity."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.models.base import SourceInfo, validate_http_url, validate_timezone_aware


class ResearchPaperContent(BaseModel):
    """Core content for research paper records."""

    title: str = Field(
        ...,
        min_length=1,
        description="Title of the research paper",
    )
    authors: list[str] = Field(
        ...,
        min_length=1,
        description="List of author names",
    )
    paper_url: str = Field(
        ...,
        description="Link to the Arxiv/PDF page",
    )
    github_url: str | None = Field(
        default=None,
        description="Link to the associated code repository (if any)",
    )
    github_stars: int | None = Field(
        default=None,
        ge=0,
        description="Current number of stars on the GitHub repository",
    )
    published_date: datetime = Field(
        ...,
        description="Timezone-aware ISO-8601 publication date",
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Title cannot be blank")
        return cleaned

    @field_validator("authors")
    @classmethod
    def validate_authors(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Authors list cannot be empty")
        cleaned = [a.strip() for a in v if isinstance(a, str) and a.strip()]
        if not cleaned:
            raise ValueError("Authors list must contain at least one valid author name")
        return cleaned

    @field_validator("paper_url")
    @classmethod
    def validate_paper_url(cls, v: str) -> str:
        validated = validate_http_url(v)
        if validated is None:
            raise ValueError("paper_url cannot be empty")
        return validated

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_http_url(v)

    @field_validator("published_date")
    @classmethod
    def validate_published_date(cls, v: datetime) -> datetime:
        validated = validate_timezone_aware(v)
        if validated is None:
            raise ValueError("published_date cannot be null")
        return validated


class ResearchPaper(BaseModel):
    """Canonical research paper entity model."""

    schemaVersion: str = Field(
        default="1.0",
        description="Versioning for the schema (e.g., '1.0')",
    )
    recordType: Literal["RESEARCH_PAPER"] = Field(
        default="RESEARCH_PAPER",
        description="Fixed to 'RESEARCH_PAPER'",
    )
    source_info: SourceInfo | None = Field(
        default=None,
        description="Provenance information for the paper",
    )
    content: ResearchPaperContent = Field(
        ..., description="Research paper payload",
    )
