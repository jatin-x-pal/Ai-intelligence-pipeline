"""PostgreSQL connection pool management using asyncpg.

Provides a singleton-style pool that is created once at startup
and shared across all pipeline stages via dependency injection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import asyncpg

if TYPE_CHECKING:
    from src.config import PostgresSettings
from src.logging_config import get_logger

logger = get_logger(__name__)


class DatabasePool:
    """Manages an asyncpg connection pool lifecycle.

    Usage:
        pool = DatabasePool(settings.postgres)
        await pool.connect()
        try:
            row = await pool.fetchrow("SELECT 1 AS ok")
        finally:
            await pool.disconnect()
    """

    def __init__(self, settings: PostgresSettings) -> None:
        self._settings = settings
        self._pool: asyncpg.Pool[asyncpg.Record] | None = None

    @property
    def pool(self) -> asyncpg.Pool[asyncpg.Record]:
        """Return the active connection pool or raise if not connected."""
        if self._pool is None:
            msg = "Database pool is not connected. Call connect() first."
            raise RuntimeError(msg)
        return self._pool

    async def connect(
        self,
        min_size: int = 2,
        max_size: int = 10,
    ) -> None:
        """Create the connection pool.

        Args:
            min_size: Minimum number of connections to maintain.
            max_size: Maximum number of connections in the pool.
        """
        if self._pool is not None:
            logger.warning("database_pool_already_connected")
            return

        logger.info(
            "database_connecting",
            host=self._settings.host,
            port=self._settings.port,
            database=self._settings.db,
        )

        self._pool = await asyncpg.create_pool(
            dsn=self._settings.dsn,
            min_size=min_size,
            max_size=max_size,
        )

        logger.info("database_connected", pool_size=max_size)

    async def disconnect(self) -> None:
        """Close all connections in the pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("database_disconnected")

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a SQL statement."""
        return await self.pool.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """Execute a query and return all rows."""
        return await self.pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        """Execute a query and return a single row."""
        return await self.pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        """Execute a query and return a single value."""
        return await self.pool.fetchval(query, *args)

    async def health_check(self) -> bool:
        """Check database connectivity. Returns True if healthy."""
        try:
            result = await self.fetchval("SELECT 1")
            return result == 1
        except Exception as exc:
            logger.exception("database_health_check_failed", exception=exc)
            return False
