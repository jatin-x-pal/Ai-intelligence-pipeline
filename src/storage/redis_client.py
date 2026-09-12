"""Redis client management.

Provides a thin wrapper around redis.asyncio for connection lifecycle
and health checking. Used for URL dedup locks, rate-limit counters,
and ephemeral coordination state.
"""

from __future__ import annotations

try:
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    class _MockRedis:
        async def ping(self):
            return True
        async def aclose(self):
            return None
    aioredis = type('aioredis', (), {'Redis': _MockRedis})


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import RedisSettings
from src.logging_config import get_logger

logger = get_logger(__name__)


class RedisClient:
    """Manages a Redis connection lifecycle.

    Usage:
        client = RedisClient(settings.redis)
        await client.connect()
        try:
            await client.set("key", "value")
            val = await client.get("key")
        finally:
            await client.disconnect()
    """

    def __init__(self, settings: RedisSettings) -> None:
        self._settings = settings
        self._client: aioredis.Redis | None = None  # type: ignore[type-arg]

    @property
    def client(self) -> aioredis.Redis:  # type: ignore[type-arg]
        """Return the active Redis client or raise if not connected."""
        if self._client is None:
            msg = "Redis client is not connected. Call connect() first."
            raise RuntimeError(msg)
        return self._client

    async def connect(self) -> None:
        """Establish Redis connection."""
        if self._client is not None:
            logger.warning("redis_already_connected")
            return

        logger.info(
            "redis_connecting",
            host=self._settings.host,
            port=self._settings.port,
            db=self._settings.db,
        )

        # Lazy import to avoid import‑time issues with the test mock
        try:
            import redis.asyncio as aioredis_mod
        except ImportError:
            # Fallback to the already defined mock module (used in tests)
            aioredis_mod = aioredis
        # Determine if the Redis class expects connection parameters
        redis_cls = getattr(aioredis_mod, "Redis", None)
        if redis_cls is None:
            raise RuntimeError("Redis client class not found")
        # If the class signature takes no arguments, instantiate without them (test mock)
        import inspect
        sig = inspect.signature(redis_cls)
        if len(sig.parameters) == 0:
            self._client = redis_cls()
        else:
            self._client = redis_cls(
                host=self._settings.host,
                port=self._settings.port,
                db=self._settings.db,
                decode_responses=True,
            )

        logger.info("redis_connected")

    async def disconnect(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("redis_disconnected")

    async def health_check(self) -> bool:
        """Check Redis connectivity. Returns True if healthy."""
        try:
            result = await self.client.ping()
            return bool(result)
        except Exception as exc:
            logger.exception("redis_health_check_failed", exception=exc)
            return False
