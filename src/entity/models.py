from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, Field


class EntityMappingLog(BaseModel):
    """Log entry describing how a raw entity name was resolved.

    All fields are immutable after creation - the model is used as a plain data container.
    """

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
        default_factory=lambda: datetime.utcnow(),
        description="UTC timestamp when the mapping was created",
    )

    class Config:
        allow_mutation = False
        frozen = True
        json_encoders: ClassVar[dict] = {datetime: lambda v: v.isoformat() + "Z"}
