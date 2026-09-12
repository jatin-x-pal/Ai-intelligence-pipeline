"""Tests for structured logging configuration."""

from __future__ import annotations

import logging

from src.logging_config import configure_logging, get_logger


class TestLoggingConfiguration:
    """Test structlog setup."""

    def test_configure_sets_log_level(self) -> None:
        configure_logging("DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_configure_info_level(self) -> None:
        configure_logging("INFO")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_configure_invalid_level_defaults_to_info(self) -> None:
        configure_logging("INVALID_LEVEL")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_get_logger_returns_bound_logger(self) -> None:
        configure_logging("INFO")
        log = get_logger("test.module")
        # structlog BoundLogger should be usable
        assert log is not None

    def test_noisy_loggers_quieted(self) -> None:
        configure_logging("DEBUG")
        assert logging.getLogger("asyncio").level == logging.WARNING
        assert logging.getLogger("asyncpg").level == logging.WARNING

    def test_logger_can_emit_without_error(self) -> None:
        configure_logging("DEBUG")
        log = get_logger("test")
        # Should not raise
        log.info("test_event", key="value", number=42)

    def test_logger_with_context(self) -> None:
        configure_logging("INFO")
        log = get_logger("test.context")
        bound = log.bind(url="https://example.com", source="test")
        # Should not raise
        bound.info("context_test")
