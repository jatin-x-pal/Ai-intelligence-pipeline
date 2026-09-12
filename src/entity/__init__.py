"""Entity resolution package public API.

Provides :func:`resolve_entity` for deterministic canonicalization.
"""

from .models import EntityMappingLog
from .resolution import resolve_entity

__all__ = ["EntityMappingLog", "resolve_entity"]
