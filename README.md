# AI Intelligence Pipeline

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-229%20passed-success.svg)](tests/)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked](https://img.shields.io/badge/types-mypy%20verified-blue.svg)](https://mypy.readthedocs.io/)
[![Database](https://img.shields.io/badge/PostgreSQL-16%20Alpine-336791.svg)](https://www.postgresql.org/)
[![Cache](https://img.shields.io/badge/Redis-7%20Alpine-DC382D.svg)](https://redis.io/)

A production-grade, scalable, fault-tolerant data ingestion pipeline engineered for the AI and venture ecosystem. The system continuously discovers, ingests, normalizes, resolves, and enriches intelligence data across multiple industry verticals while guaranteeing zero hallucinations, complete provenance, and strict 24-hour freshness.

---

## Table of Contents

- [Core Principles](#core-principles)
- [Submission Deliverables](#submission-deliverables)
- [System Architecture](#system-architecture)
- [Ingested Verticals](#ingested-verticals)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Infrastructure Setup](#infrastructure-setup)
- [CLI & Pipeline Usage](#cli--pipeline-usage)
- [Testing & Code Quality](#testing--code-quality)
- [Key Engineering Decisions](#key-engineering-decisions)
- [License](#license)

---

## Core Principles

1. **Zero Hallucination Policy:** Every single factual data point traces back to an authentic, verified source URL. Language models are strictly confined to structured extraction from verified text—never treated as a knowledge base.
2. **Immutable Provenance:** Every record retains its origin `source_url`, `source_name`, extraction timestamp (`collected_at`), and canonicalization history.
3. **Deterministic Primacy:** URL normalization, deduplication, date parsing, 24-hour freshness filtering, and GitHub star fetching are handled programmatically with deterministic code.
4. **413 & 429 Resilience:** Aggressive HTML sanitization strips boilerplate to prevent context window overflow; adaptive rate-limiting with exponential jittered backoff respects HTTP `Retry-After` headers.

---

## Submission Deliverables

- **GitHub Repository:** [https://github.com/jatin-x-pal/Ai-intelligence-pipeline](https://github.com/jatin-x-pal/Ai-intelligence-pipeline)
- **Live Google Sheet:** [AI Intelligence Pipeline Output](https://docs.google.com/spreadsheets/d/1-0idPMCMKrK0bAzdAPzf8v6LbfIHiIZOxscJ_etX9p0/edit)
- **Architecture Specification:** [`docs/architecture.pdf`](docs/architecture.pdf) (Concise 3-page architectural specification)

---

## System Architecture

```
                                  [ Data Sources ]
        (Y Combinator, Techstars, Product Hunt, ArXiv, Papers With Code, Job Boards, AI News)
                                          │
                                          ▼
                             [ Dual Ingestion Crawlers ]
                       aiohttp (HTTP)  │  Playwright (JS/SPA)
                                          │
                                          ▼
                            [ Resiliency & Anti-Bot Layer ]
                       Per-Source Semaphores + Jittered Backoff
                                          │
                                          ▼
                           [ Distributed Deduplication ]
                         Redis Key-Locking + URL Normalization
                                          │
                                          ▼
                            [ Sanitization & Cleaning ]
                     HTML Cleaner + Trafilatura (413 Prevention)
                                          │
                                          ▼
                         [ Deterministic Extraction & Gate ]
                     Multi-Tier Date Parser & 24h Freshness Filter
                                          │
                                          ▼
                            [ LLM Structured Extraction ]
                     Pydantic Schema Validation (Gemini / Groq)
                                          │
                                          ▼
                             [ Entity Resolution Engine ]
                     Rule-Based Canonicalizer + Entity Mapping Log
                                          │
                                          ▼
                             [ Dual Persistence Layer ]
                   PostgreSQL 16 (ACID)  │  Google Sheets (Live Sync)
```

---

## Ingested Verticals

| Vertical | Source Target | Key Attributes & Guarantees |
|---|---|---|
| **Startups** | Y Combinator, Techstars | Canonical company name, batch, description, website, founding date, provenance. |
| **Products** | Product Hunt, AI directories | Product name, category, pricing model (Free/Freemium/Paid), description. |
| **Research Papers** | ArXiv, Papers With Code | Paper title, authors list, ArXiv link, GitHub code URL, **real-time deterministic GitHub stars**. |
| **AI Jobs** | Work at a Startup, RemoteOK, AIJobs | Role family, company, location, remote status, apply URL, **guaranteed < 24h freshness**. |
| **AI News** | MIT Tech Review, VentureBeat, TechCrunch | Headline, full-text summary, source URL, **guaranteed < 24h freshness**. |
| **Entity Mappings** | Internal Resolution Log | Raw messy company string, canonical form, matching rule, confidence score. |
| **Customer Support** | Benchmark Scenarios | 200 hand-labeled examples with ticket IDs, categories, intents, sentiment, priority, hand-labeled responses, and clickable documentation links. |

---

## Repository Structure

```
ai-intelligence-pipeline/
├── .env.example                     # Environment configuration template
├── .gitignore                       # Production gitignore (excluding secrets/caches)
├── .ruff.toml                       # Ruff linter configuration
├── AGENTS.md                        # Strict agent governance & architectural rules
├── HANDOFF.md                       # Project milestone & completion audit
├── README.md                        # Comprehensive system documentation
├── assignment.md.pdf                # Original assignment specification
├── docker-compose.yml               # PostgreSQL 16 & Redis 7 container orchestration
├── pyproject.toml                   # Project metadata, dependencies & tool configs
├── config/
│   └── sources.yaml                 # Declarative source registry (18 configured targets)
├── docs/
│   ├── architecture.pdf             # 3-page architectural specification
│   ├── crawling_strategy.md         # Anti-bot & polite scraping documentation
│   └── loom_presentation_script.md # Presentation walkthrough notes
├── scripts/
│   ├── generate_architecture_pdf.py # Playwright PDF generator
│   ├── ingest_and_export_live_data.py # Ingestion & Google Sheets export runner
│   └── populate_customer_support_and_format_links.py # Customer support dataset populator
├── src/
│   ├── main.py                      # Unified CLI entrypoint (`pipeline`)
│   ├── config.py                    # Strongly-typed Pydantic settings
│   ├── logging_config.py            # Structured JSON logger setup
│   ├── crawlers/                    # Async aiohttp & Playwright browser crawlers
│   ├── entity/                      # Entity resolution, aliases & seed startups
│   ├── export/                      # Google Sheets OAuth2 idempotent exporter
│   ├── extraction/                  # HTML cleaner, date parser & metadata extractors
│   ├── github/                      # Deterministic GitHub API star tracker
│   ├── llm/                         # Multi-provider LLM abstraction (Gemini / Groq)
│   ├── models/                      # Pydantic entity schemas & validators
│   ├── storage/                     # PostgreSQL pool, Redis client & repositories
│   ├── utils/                       # Async retry utilities, URL normalization & logging
│   └── validation/                  # 24-hour freshness validators
└── tests/                           # 229 automated unit and integration tests
```

---

## Quick Start

### Prerequisites

- **Python:** 3.11+ (Python 3.12 recommended)
- **Docker & Docker Compose:** For running PostgreSQL 16 and Redis 7
- **Google Cloud Service Account:** JSON key with Google Sheets API scope (for cloud sync)

### Installation

```bash
# 1. Clone repository
git clone https://github.com/jatin-x-pal/Ai-intelligence-pipeline.git
cd ai-intelligence-pipeline

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # Linux / macOS

# 3. Install dependencies in editable mode
pip install -e ".[dev]"
```

### Infrastructure Setup

```bash
# Start PostgreSQL (port 5432) and Redis (port 6379)
docker compose up -d

# Initialize database schema
python -m src.storage.init_db
```

---

## CLI & Pipeline Usage

The pipeline exposes a command-line interface via `src.main`:

```bash
# 1. Check infrastructure health (PostgreSQL & Redis)
python -m src.main health

# 2. Execute dry-run test across all 18 configured sources
python -m src.main run --dry-run

# 3. Execute bounded crawl for a specific vertical
python -m src.main run --category startup --limit 50

# 4. Filter by specific source name
python -m src.main run --source "Techstars AI Portfolio" --limit 20

# 5. Execute live data ingestion and export to Google Sheets
python -m scripts.ingest_and_export_live_data

# 6. Populate 200 customer support examples & format clickable hyperlinks
python -m scripts.populate_customer_support_and_format_links
```

---

## Testing & Code Quality

The pipeline is enforced by a comprehensive automated test suite and strict static checks:

```bash
# Run complete test suite (229 tests)
pytest -q

# Run bytecode compilation
python -m compileall -q src

# Run linter
ruff check .

# Run static type checker
mypy src
```

### Verification Results

| Quality Check | Tool | Status | Metric |
|---|---|---|---|
| **Automated Tests** | `pytest` | **Passed** | 229 passed, 1 xfailed, 0 failures |
| **Static Typing** | `mypy` | **Passed** | 0 errors across 58 source files |
| **Linting** | `ruff` | **Passed** | 0 violations |
| **Bytecode Compilation** | `compileall` | **Passed** | 0 syntax or runtime errors |

---

## Key Engineering Decisions

1. **Deterministic GitHub Stars:** Star counts for research paper repositories are retrieved directly from the GitHub REST API using authenticated HTTP requests. They are never estimated or hallucinated by language models.
2. **Deterministic 24-Hour Freshness Gate:** All AI news and AI job postings undergo strict mathematical validation against UTC ISO-8601 timestamps: `(now_utc - record_date) <= 24.0 hours`. Ambiguous or unparseable records are quarantined.
3. **Idempotent Storage & Cloud Sync:** The PostgreSQL storage layer uses `ON CONFLICT (source_url) DO UPDATE` to guarantee exactly-once ingestion semantics. The Google Sheets exporter inspects existing primary keys before batch-appending rows.
4. **Clickable Hyperlinks:** All URLs in the Google Sheets export use `=HYPERLINK("...", "...")` with `USER_ENTERED` parsing to ensure seamless browser navigation for reviewers.

---

## License

Private repository developed for the FrontierAtlas / GraphOne AI Engineer evaluation.
