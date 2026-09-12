"""Database schema initialization.

Creates tables for all 5 entity types and the entity mapping log with appropriate
constraints, types, and indexes.
"""

import asyncio

from src.config import get_settings
from src.storage.database import DatabasePool

DDL_STATEMENTS = """
CREATE TABLE IF NOT EXISTS startups (
    source_url TEXT PRIMARY KEY,
    source_name TEXT,
    collected_at TIMESTAMPTZ,
    name TEXT,
    description TEXT,
    website TEXT,
    founded_date TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS products (
    source_url TEXT PRIMARY KEY,
    source_name TEXT,
    collected_at TIMESTAMPTZ,
    name TEXT,
    description TEXT,
    category TEXT,
    price TEXT
);

CREATE TABLE IF NOT EXISTS research_papers (
    source_url TEXT PRIMARY KEY,
    source_name TEXT,
    collected_at TIMESTAMPTZ,
    title TEXT,
    authors TEXT,
    publication_date TIMESTAMPTZ,
    paper_url TEXT,
    github_url TEXT,
    github_stars INTEGER
);

CREATE TABLE IF NOT EXISTS jobs (
    source_url TEXT PRIMARY KEY,
    source_name TEXT,
    collected_at TIMESTAMPTZ,
    title TEXT,
    company TEXT,
    location TEXT,
    posted_date TIMESTAMPTZ,
    apply_url TEXT
);

CREATE TABLE IF NOT EXISTS news (
    source_url TEXT PRIMARY KEY,
    source_name TEXT,
    collected_at TIMESTAMPTZ,
    title TEXT,
    content TEXT,
    publication_date TIMESTAMPTZ,
    url TEXT
);

CREATE TABLE IF NOT EXISTS entity_mappings (
    raw_name TEXT PRIMARY KEY,
    canonical_name TEXT,
    matching_method TEXT,
    confidence FLOAT,
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

async def init_schema():
    settings = get_settings()
    db = DatabasePool(settings.postgres)
    await db.connect()
    try:
        await db.execute(DDL_STATEMENTS)
        print("Schema successfully initialized!")
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(init_schema())
