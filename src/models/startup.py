"""Canonical Pydantic schema for Startup entity."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.models.base import SourceInfo, validate_timezone_aware


class StartupData(BaseModel):
    """Metadata for startup entities."""

    employeeCount: int | None = Field(
        default=None,
        ge=0,
        description="Number of employees (if available)",
    )


class StartupContent(BaseModel):
    """Core content for startup records."""

    entityName: str = Field(
        ...,
        min_length=1,
        description="Canonical startup name",
    )
    data: StartupData = Field(
        default_factory=StartupData,
        description="Startup metadata",
    )

    @field_validator("entityName")
    @classmethod
    def validate_entity_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Entity name cannot be blank")
        return cleaned


class Startup(BaseModel):
    # Existing fields...
    # Provide direct attribute access for backwards compatibility with older tests
    @property
    def entityName(self) -> str:
        """Alias for content.entityName for legacy test compatibility."""
        return self.content.entityName

    @property
    def data(self) -> StartupData:
        """Alias for content.data for legacy test compatibility."""
        return self.content.data
    """Canonical startup entity model."""

    schemaVersion: str = Field(
        default="1.0",
        description="Versioning for the schema (e.g., '1.0')",
    )
    recordType: Literal["STARTUP"] = Field(
        default="STARTUP",
        description="Fixed to 'STARTUP'",
    )
    source: SourceInfo = Field(
        ...,
        description="Source site name and original URL",
    )
    content: StartupContent = Field(
        ...,
        description="Startup payload containing entityName and data",
    )
    collectedAt: datetime = Field(
        ...,
        description="Timezone-aware ISO-8601 collection timestamp",
    )

    @field_validator("collectedAt", mode="before")
    @classmethod
    def validate_collected_at(cls, v: datetime) -> datetime:
        validated = validate_timezone_aware(v)
        if validated is None:
            raise ValueError("collectedAt cannot be null")
        return validated
