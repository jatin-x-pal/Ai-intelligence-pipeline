# src/storage/repositories.py
# ruff: noqa
"""Repository layer for persisting validated entities.

All entities are validated by the Pydantic schemas before they reach this
layer, so the repository merely stores the dict representation while
preserving provenance fields (`source_url`, `collected_at`, etc.).

Each repository provides an ``upsert`` method that performs an ``INSERT
... ON CONFLICT (source_url) DO UPDATE`` to guarantee idempotent ingestion.
The implementation is async and re‑uses the existing ``DatabasePool``
connection pool.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from src.logging_config import get_logger
from src.storage.database import DatabasePool

logger = get_logger(__name__)

# Mapping of entity type to table name - keep in sync with migrations.
_TABLE_MAP: Mapping[type[BaseModel], str] = {
    # The actual Pydantic models live in ``src.models`` and are re‑exported
    # from ``src.schemas``; we accept any subclass of BaseModel here.
    # The concrete types are imported lazily inside the methods to avoid
    # circular imports.
}


class BaseRepository:
    """Common functionality for all entity repositories."""

    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    @staticmethod
    def _entity_to_dict(entity: BaseModel) -> dict[str, Any]:
        """Convert a Pydantic model to a plain ``dict`` for SQL insertion.

        ``exclude_unset`` ensures that only fields present in the validated
        model are written. ``by_alias`` respects any JSON field aliases the
        model defines.
        """
        return entity.model_dump(exclude_unset=True, by_alias=True)

    async def _upsert(self, table: str, data: dict[str, Any]) -> None:
        """Perform an ``INSERT … ON CONFLICT`` upsert.

        The conflict target is ``source_url`` - every entity schema includes
        this field (or a deterministic equivalent). All other columns are
        updated on conflict, preserving ``source_url``.
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f"${i}" for i in range(1, len(data) + 1))
        # Build the ON CONFLICT SET clause (exclude source_url).
        set_clause_parts = []
        # idx variable removed as it was unused
        for col in data:
            if col == "source_url":
                continue
            set_clause_parts.append(f"{col} = EXCLUDED.{col}")
        set_clause = ", ".join(set_clause_parts) if set_clause_parts else ""
        sql = (
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT (source_url) DO UPDATE SET {set_clause}"
        )
        logger.debug("upsert_sql", sql=sql, data=data)
        await self._db.execute(sql, *data.values())


# Concrete repositories - each knows its table name.

class StartupRepository(BaseRepository):
    async def upsert(self, entity: BaseModel) -> None:
        from src.schemas import Startup

        if not isinstance(entity, Startup):
            raise TypeError("StartupRepository expects a Startup model")
        data = self._entity_to_dict(entity)
        await self._upsert("startups", data)


class ProductRepository(BaseRepository):
    async def upsert(self, entity: BaseModel) -> None:
        from src.schemas import Product

        if not isinstance(entity, Product):
            raise TypeError("ProductRepository expects a Product model")
        data = self._entity_to_dict(entity)
        await self._upsert("products", data)


class ResearchPaperRepository(BaseRepository):
    async def upsert(self, entity: BaseModel) -> None:
        from src.schemas import ResearchPaper

        if not isinstance(entity, ResearchPaper):
            raise TypeError("ResearchPaperRepository expects a ResearchPaper model")
        data = self._entity_to_dict(entity)
        await self._upsert("research_papers", data)


class JobRepository(BaseRepository):
    async def upsert(self, entity: BaseModel) -> None:
        from src.schemas import Job

        if not isinstance(entity, Job):
            raise TypeError("JobRepository expects a Job model")
        data = self._entity_to_dict(entity)
        await self._upsert("jobs", data)


class NewsRepository(BaseRepository):
    async def upsert(self, entity: BaseModel) -> None:
        from src.schemas import News

        if not isinstance(entity, News):
            raise TypeError("NewsRepository expects a News model")
        data = self._entity_to_dict(entity)
        await self._upsert("news", data)


class EntityMappingRepository(BaseRepository):
    async def upsert(self, entity: BaseModel) -> None:
        from src.schemas import EntityMapping

        if not isinstance(entity, EntityMapping):
            raise TypeError("EntityMappingRepository expects an EntityMapping model")
        data = self._entity_to_dict(entity)
        await self._upsert("entity_mappings", data)

# Export for easy import elsewhere
__all__ = [
    "EntityMappingRepository",
    "JobRepository",
    "NewsRepository",
    "ProductRepository",
    "ResearchPaperRepository",
    "StartupRepository",
]
