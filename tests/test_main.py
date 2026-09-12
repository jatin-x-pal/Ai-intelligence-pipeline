"""Tests for the CLI entry point and health check."""

from __future__ import annotations

from unittest import mock

import pytest

from src.main import build_parser


class TestCLI:
    """Test CLI argument parsing."""

    def test_health_command_parsed(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["health"])
        assert args.command == "health"

    def test_run_command_options_parsed(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "run",
            "--source", "Techstars AI Portfolio",
            "--category", "startup",
            "--limit", "10",
            "--dry-run",
        ])
        assert args.command == "run"
        assert args.source == "Techstars AI Portfolio"
        assert args.category == "startup"
        assert args.limit == 10
        assert args.dry_run is True

    @pytest.mark.asyncio
    async def test_health_check_mocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.main import health_check
        monkeypatch.setattr("src.storage.database.DatabasePool.connect", mock.AsyncMock())
        monkeypatch.setattr("src.storage.database.DatabasePool.health_check", mock.AsyncMock(return_value=True))
        monkeypatch.setattr("src.storage.database.DatabasePool.disconnect", mock.AsyncMock())
        monkeypatch.setattr("src.storage.redis_client.RedisClient.connect", mock.AsyncMock())
        monkeypatch.setattr("src.storage.redis_client.RedisClient.health_check", mock.AsyncMock(return_value=True))
        monkeypatch.setattr("src.storage.redis_client.RedisClient.disconnect", mock.AsyncMock())

        healthy = await health_check()
        assert healthy is True

    @pytest.mark.asyncio
    async def test_run_pipeline_orchestration_mocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.main import build_parser, run_pipeline
        parser = build_parser()
        args = parser.parse_args(["run", "--dry-run", "--limit", "5"])

        monkeypatch.setattr("src.storage.database.DatabasePool.connect", mock.AsyncMock())
        monkeypatch.setattr("src.storage.database.DatabasePool.disconnect", mock.AsyncMock())

        # Should complete without error
        await run_pipeline(args)
