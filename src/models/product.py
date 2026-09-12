"""Canonical Pydantic schema for Product entity."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.models.base import SourceInfo, validate_timezone_aware


class PricingModel(StrEnum):
    """Allowed pricing models for products."""

    FREE = "FREE"
    FREEMIUM = "FREEMIUM"
    PAID = "PAID"
    ENTERPRISE = "ENTERPRISE"


class ProductContent(BaseModel):
    """Core content for product records."""

    startupName: str = Field(
        ...,
        min_length=1,
        description="Canonical startup name",
    )
    pricingModel: PricingModel = Field(
        ...,
        description="Pricing model (FREE, FREEMIUM, PAID, ENTERPRISE)",
    )

    @field_validator("startupName")
    @classmethod
    def validate_startup_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Startup name cannot be blank")
        return cleaned


class Product(BaseModel):
    """Canonical product entity model."""

    schemaVersion: str = Field(
        default="1.0",
        description="Versioning for the schema (e.g., '1.0')",
    )
    recordType: Literal["PRODUCT"] = Field(
        default="PRODUCT",
        description="Fixed to 'PRODUCT'",
    )
    source: SourceInfo = Field(
        ...,
        description="Source site name and original URL",
    )
    content: ProductContent = Field(
        ...,
        description="Product payload containing startupName and pricingModel",
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
