"""Storage layer — database, cache connections, and deduplication.
"""

from src.storage.database import DatabasePool
from src.storage.dedup import BaseDeduplicator, InMemoryDeduplicator

# Optional Redis client import; if redis library is not installed, set RedisClient to None.
try:
    from src.storage.redis_client import RedisClient
except ModuleNotFoundError:  # pragma: no cover
    RedisClient = None  # type: ignore

__all__ = [
    "BaseDeduplicator",
    "DatabasePool",
    "InMemoryDeduplicator",
    "RedisClient",
]
