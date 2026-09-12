"""Structured logging utilities for crawler and pipeline components."""

from typing import Any

import structlog

from src.logging_config import get_logger as get_base_logger


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance bound to a module or component name.

    Args:
        name: Logger name, defaults to None.

    Returns:
        A structlog BoundLogger instance.
    """
    return get_base_logger(name)


def bind_context(logger: structlog.stdlib.BoundLogger, **kwargs: Any) -> structlog.stdlib.BoundLogger:
    """Bind additional context fields (e.g. url, attempt, stage) to the logger.

    Args:
        logger: Existing BoundLogger.
        **kwargs: Key-value context to bind.

    Returns:
        New BoundLogger with context attached.
    """
    return logger.bind(**kwargs)
