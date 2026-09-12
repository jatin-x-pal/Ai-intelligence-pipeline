"""Canonical Pydantic schema for Job entity."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.models.base import validate_timezone_aware


class JobContent(BaseModel):
    """Core content for job posting records."""

    company: str = Field(
        ...,
        min_length=1,
        description="Canonical company name",
    )
    date: datetime = Field(
        ...,
        description="Timezone-aware ISO-8601 publication date",
    )
    is_remote: bool = Field(
        ...,
        description="Remote eligibility",
    )
    role_family: str = Field(
        ...,
        min_length=1,
        description="Functional category (e.g., 'Engineering')",
    )

    @field_validator("company")
    @classmethod
    def validate_company(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Company name cannot be blank")
        return cleaned

    @field_validator("role_family")
    @classmethod
    def validate_role_family(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Role family cannot be blank")
        return cleaned

    @field_validator("date")
    @classmethod
    def validate_job_date(cls, v: datetime) -> datetime:
        validated = validate_timezone_aware(v)
        if validated is None:
            raise ValueError("Date cannot be null")
        return validated


class Job(BaseModel):
    """Canonical job entity model."""

    schemaVersion: str = Field(
        default="1.0",
        description="Versioning for the schema (e.g., '1.0')",
    )
    recordType: Literal["JOB"] = Field(
        default="JOB",
        description="Fixed to 'JOB'",
    )
    content: JobContent = Field(
        ...,
        description="Job posting payload",
    )
