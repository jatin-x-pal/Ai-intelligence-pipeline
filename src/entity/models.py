from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class EntityMappingLog(BaseModel):
    """Log entry describing how a raw entity name was resolved.

    All fields are immutable after creation - the model is used as a plain data container.
    """

    model_config = ConfigDict(frozen=True)

    raw_name: str = Field(..., description="The original name as extracted from the source")
    canonical_name: str | None = Field(
        None,
        description="The deterministic canonical name, if resolution succeeded",
    )
    match_reason: str = Field(..., description="Reason/rule that produced the match")
    source: str | None = Field(
        None,
        description="Optional provenance identifier (e.g., URL, source name)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the mapping was created",
    )
