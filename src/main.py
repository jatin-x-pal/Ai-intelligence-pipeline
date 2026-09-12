"""Application entry point and CLI.

Provides the `pipeline` command with subcommands:
  - health: Check connectivity to PostgreSQL and Redis.
  - run: Execute the full pipeline (future).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from src.config import get_settings
from src.crawlers.pipeline import SourceCrawlPipeline
from src.export.google_sheets import exporter as google_sheets_exporter
from src.logging_config import configure_logging, get_logger
from src.storage.database import DatabasePool
from src.storage.redis_client import RedisClient
from src.storage.repositories import (
    JobRepository,
    NewsRepository,
    ProductRepository,
    ResearchPaperRepository,
    StartupRepository,
)

logger = get_logger(__name__)


async def health_check() -> bool:
    """Verify connectivity to all infrastructure services.

    Returns:
        True if all services are reachable, False otherwise.
    """
    settings = get_settings()
    db = DatabasePool(settings.postgres)
    cache = RedisClient(settings.redis)

    results: dict[str, bool] = {}

    try:
        # PostgreSQL
        try:
            await db.connect(min_size=1, max_size=2)
            results["postgresql"] = await db.health_check()
        except Exception as exc:
            logger.exception("health_check_postgres_error", exception=exc)
            results["postgresql"] = False

        # Redis
        try:
            await cache.connect()
            results["redis"] = await cache.health_check()
        except Exception as exc:
            logger.exception("health_check_redis_error", exception=exc)
            results["redis"] = False

    finally:
        await db.disconnect()
        await cache.disconnect()

    # Report
    all_healthy = True
    for service, healthy in results.items():
        status = "healthy" if healthy else "unhealthy"
        logger.info("health_check_result", service=service, status=status, healthy=healthy)
        if not healthy:
            all_healthy = False

    return all_healthy


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="AI Intelligence Pipeline — data ingestion system",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # health subcommand
    subparsers.add_parser("health", help="Check infrastructure connectivity")

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Execute the full ingestion pipeline")
    run_parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Filter to a specific source name (optional)",
    )
    run_parser.add_argument(
        "--category",
        type=str,
        choices=["startup", "product", "research", "news", "job"],
        default=None,
        help="Filter to a source category",
    )
    run_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of records to process per source (default unlimited)",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute pipeline without persisting or exporting (useful for CI)",
    )

    return parser


async def run_pipeline(args: argparse.Namespace) -> None:
    """Orchestrate the full ingestion pipeline.

    Respects CLI options defined in ``build_parser``.
    """
    settings = get_settings()
    db = DatabasePool(settings.postgres)
    await db.connect(min_size=1, max_size=5)

    # Initialize repositories
    startup_repo = StartupRepository(db)
    product_repo = ProductRepository(db)
    research_repo = ResearchPaperRepository(db)
    job_repo = JobRepository(db)
    news_repo = NewsRepository(db)
    # entity_repo removed (unused)

    async with SourceCrawlPipeline() as pipeline:
        registry = pipeline.registry
        sources = registry.get_sources(category=args.category, enabled_only=True)
        if args.source:
            sources = [s for s in sources if s.name == args.source]

        # Import crawler classes
        from src.crawlers.job import JobCrawler
        from src.crawlers.news import NewsCrawler
        from src.crawlers.product import ProductCrawler
        from src.crawlers.research import ResearchCrawler
        from src.crawlers.startup import StartupCrawler
        from src.schemas import Job, News, Product, ResearchPaper, Startup

        crawler_map = {
            "startup": StartupCrawler,
            "product": ProductCrawler,
            "research": ResearchCrawler,
            "job": JobCrawler,
            "news": NewsCrawler,
        }

        export_data: dict[str, list[Any]] = {
            "Startups": [],
            "Products": [],
            "Research Papers": [],
            "Jobs": [],
            "News": [],
            "Entity Mapping Log": [],
        }

        for src_cfg in sources:
            cat = src_cfg.category.value
            crawler_cls = crawler_map.get(cat)
            if not crawler_cls:
                logger.warning("run_unknown_category", category=cat)
                continue
            crawler = crawler_cls(pipeline)  # type: ignore
            if args.dry_run:
                logger.info("dry_run: skipping crawling for source", source=src_cfg.name)
                continue
            items = await crawler.crawl(src_cfg.name)
            if not items:
                continue
            if not isinstance(items, list):
                items = [items]
            if args.limit is not None:
                items = items[: args.limit]

            for item in items:
                if isinstance(item, Startup):
                    await startup_repo.upsert(item)
                    export_data["Startups"].append(item)
                elif isinstance(item, Product):
                    await product_repo.upsert(item)
                    export_data["Products"].append(item)
                elif isinstance(item, ResearchPaper):
                    await research_repo.upsert(item)
                    export_data["Research Papers"].append(item)
                elif isinstance(item, Job):
                    await job_repo.upsert(item)
                    export_data["Jobs"].append(item)
                elif isinstance(item, News):
                    await news_repo.upsert(item)
                    export_data["News"].append(item)
                else:
                    logger.warning("run_unexpected_model", model=type(item).__name__)

    await db.disconnect()

    if not args.dry_run:
        exporter = google_sheets_exporter
        if exporter is None:
            logger.error("google_sheets_exporter_not_initialized")
            return
        payload = {k: v for k, v in export_data.items() if v}
        await exporter.export(payload)

    logger.info(
        "pipeline_run_completed",
        sources_processed=len(sources),
        dry_run=args.dry_run,
    )


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)

    if args.command == "health":
        healthy = asyncio.run(health_check())
        sys.exit(0 if healthy else 1)
    elif args.command == "run":
        asyncio.run(run_pipeline(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
