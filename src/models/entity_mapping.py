"""Canonical Pydantic schema for EntityMapping log entry."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from src.models.base import validate_http_url, validate_timezone_aware


class EntityMapping(BaseModel):
    """Audit log entry capturing entity resolution from raw messy strings to canonical form."""

    raw_name: str = Field(
        ...,
        min_length=1,
        description="Messy or unnormalized entity name as found in the raw source",
    )
    canonical_name: str = Field(
        ...,
        min_length=1,
        description="Canonical normalized entity name",
    )
    entity_type: str = Field(
        ...,
        min_length=1,
        description="Type of entity (e.g., 'STARTUP', 'PRODUCT', 'COMPANY')",
    )
    mapping_method: str = Field(
        ...,
        min_length=1,
        description="Method used for resolution (e.g., 'exact', 'alias_dict', 'fuzzy', 'llm')",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score for the resolution (0.0 to 1.0; None if deterministic)",
    )
    source: str = Field(
        ...,
        min_length=1,
        description="Source information or site where the entity appeared",
    )
    source_url: str | None = Field(
        default=None,
        description="Optional source URL where the entity appeared",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware timestamp when the mapping was established",
    )

    @model_validator(mode="before")
    @classmethod
    def handle_source_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict) and "source" not in data:
            if "source_info" in data:
                data["source"] = data["source_info"]
            elif "source_name" in data:
                data["source"] = data["source_name"]
        return data

    @field_validator("raw_name")
    @classmethod
    def validate_raw_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("raw_name cannot be blank")
        return cleaned

    @field_validator("canonical_name")
    @classmethod
    def validate_canonical_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("canonical_name cannot be blank")
        return cleaned

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("entity_type cannot be blank")
        return cleaned

    @field_validator("mapping_method")
    @classmethod
    def validate_mapping_method(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("mapping_method cannot be blank")
        return cleaned

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("source cannot be blank")
        return cleaned

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_http_url(v)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: datetime) -> datetime:
        validated = validate_timezone_aware(v)
        if validated is None:
            raise ValueError("timestamp cannot be null")
        return validated
