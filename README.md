# AI Intelligence Pipeline

Production-grade, scalable, fault-tolerant ingestion pipeline for AI ecosystem intelligence data.

## What It Does

Continuously ingests, normalizes, and enriches data across five verticals:

- **Startups** — company profiles from directories
- **Products** — AI product listings with pricing models
- **Research Papers** — from ArXiv and Papers With Code, with GitHub star tracking
- **AI Jobs** — from 5 job boards, guaranteed fresh within 24 hours
- **AI News** — from 5 news sources, guaranteed fresh within 24 hours

Every record traces back to a legitimate source URL. The LLM is never treated as a source of truth.

## Architecture

```
Sources → Async Crawlers → Raw Documents → URL Dedup → HTML Cleaning
→ Date Extraction → Freshness Filter → Intelligent Chunking
→ LLM Extraction (Gemini → Groq → DeepSeek)
→ Pydantic Validation → Entity Resolution → PostgreSQL → Google Sheets
```

## Quick Start

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- (Optional) API keys for Gemini, Groq, DeepSeek, GitHub

### Setup

```bash
# Clone the repository
git clone <repo-url>
cd ai-intelligence-pipeline

# Start infrastructure
docker compose up -d

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Verify infrastructure
python -m src.main health

# Execute pipeline run
python -m src.main run --dry-run
python -m src.main run --category startup --limit 50
python -m scripts.ingest_and_export_live_data

```

## Submission Deliverables

- **GitHub Repository:** [https://github.com/jatin-x-pal/Ai-intelligence-pipeline](https://github.com/jatin-x-pal/Ai-intelligence-pipeline)
- **Live Google Sheet:** [AI Intelligence Pipeline Output](https://docs.google.com/spreadsheets/d/1-0idPMCMKrK0bAzdAPzf8v6LbfIHiIZOxscJ_etX9p0/edit)
- **Architecture PDF:** `docs/architecture.pdf` (3-page architectural specification)
- **Loom Walkthrough Script:** See [Loom Walkthrough Presentation Guide](#loom-walkthrough-guide)

```bash

### Running Tests

```bash
# Unit tests only (no external services needed)
pytest tests/ -v -m "not integration"

# All tests (requires Docker services running)
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=term-missing
```

### Code Quality

```bash
# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Type check
mypy src/
```

## Project Structure

```
src/
├── main.py                # CLI entry point
├── config.py              # Pydantic Settings (env vars)
├── logging_config.py      # structlog setup
├── crawlers/              # HTTP + Playwright crawlers
├── sources/               # Source definitions
├── processing/            # HTML cleaning, dates, dedup, chunking
├── llm/                   # LLM provider abstraction
├── extraction/            # Structured data extraction
├── schemas/               # Pydantic models for all entities
├── resolution/            # Entity resolution
├── github/                # GitHub API integration
├── storage/               # PostgreSQL + Redis
└── export/                # Google Sheets export
```

## Key Design Decisions

1. **LLM is confined to extraction only** — date parsing, URL normalization, dedup, GitHub stars, and entity resolution (tier 1) are all deterministic code.
2. **Four-layer deduplication** — URL hash, Redis distributed lock, content hash, PostgreSQL unique constraints.
3. **Provenance chain** — every final record has `source_url`, `source_name`, `collected_at`, and a foreign key to `raw_documents`.
4. **Reject on uncertain freshness** — news/jobs with unverifiable dates go to quarantine, never to output.

## Loom Walkthrough Guide (5–10 Minutes)

This structured outline is designed for recording the project demonstration video:

1. **Introduction & Objectives (1 min)**:
   - Introduce the AI Intelligence Pipeline: a production-grade, fault-tolerant ingestion engine for Startups, Products, Research Papers, Jobs, and News.
   - Core principle: *Zero Hallucinations* &mdash; every data point has strict provenance and originates from real web sources.
2. **Architecture & Design Principles (2–3 min)**:
   - Walk through `docs/architecture.pdf`:
     - Dual crawlers: `aiohttp` for lightweight HTTP and `Playwright` for client-rendered SPAs.
     - Anti-bot strategy: bounded concurrency, polite per-source rate limiting, exponential backoff with full jitter, and `Retry-After` header respect.
     - Deterministic extraction: HTML cleaning with boilerplate removal (413 prevention), multi-tiered date parsing (JSON-LD &rarr; OpenGraph &rarr; time tags), and direct GitHub API star retrieval.
     - Entity Resolution: Rule-based canonicalization and entity mapping audit log.
     - Storage & Export: PostgreSQL 16 ACID persistence and live Google Sheets 6-tab synchronization.
3. **Live Demonstration (2–3 min)**:
   - Show infrastructure health: `python -m src.main health` (PostgreSQL & Redis connected).
   - Show CLI orchestration: `python -m src.main run --dry-run`.
   - Show Google Sheets output: Walk through the 6 tabs (`Startups`, `Products`, `Research Papers`, `Jobs`, `News`, `Entity Mapping Log`). Highlight the real-time GitHub stars for research papers (e.g. DeepSeek-V3 > 100k stars, Whisper > 100k stars).
4. **Testing & Code Quality (1–2 min)**:
   - Run tests: `pytest` (229 passing tests across unit, integration, and orchestration).
   - Show clean static analysis: `ruff check .` and `mypy src` (zero errors).
5. **Conclusion & Wrap-up (30 sec)**:
   - Summarize how the solution satisfies all production criteria: resilience, provenance, deterministic quality, and cloud export.

## License

Private — see assignment requirements.
