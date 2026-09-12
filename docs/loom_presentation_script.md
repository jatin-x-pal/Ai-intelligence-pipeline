# Loom Video Walkthrough Script (5–10 Minutes)

Use this step-by-step presentation script to record your 5–10 minute demonstration video.

---

## Video Outline & Timing Breakdown

| Section | Target Time | Key Screens / Visuals to Show |
|---|---|---|
| **1. Introduction & Overview** | 1:00 | GitHub README & Assignment Objectives |
| **2. Architecture & Design Principles** | 2:30 | `docs/architecture.pdf` (or `README.md` diagram) |
| **3. Live CLI & Pipeline Execution** | 2:30 | VS Code Terminal (`python -m src.main health` & `run`) |
| **4. Google Sheets & Data Provenance** | 2:00 | Live Google Sheets with all 6 tabs |
| **5. Test Suite & Code Quality** | 1:00 | Running `pytest`, `ruff`, and `mypy` |
| **6. Conclusion & Submission Summary** | 0:30 | Final summary slide or GitHub repository page |

---

## Detailed Speaking Script

### 1. Introduction & Problem Scope (0:00 - 1:00)
> *"Hello! Today I'm presenting the **AI Intelligence Pipeline**, a production-grade, fault-tolerant, scalable data ingestion engine built for the AI Engineer demo assignment.*
>
> *The system continuously discovers, crawls, sanitizes, resolves, and exports intelligence across five core verticals: **AI Startups**, **AI Products**, **Research Papers**, **AI Jobs**, and **AI News**, along with an **Entity Mapping Log**.*
>
> *Our design strictly adheres to non-negotiable engineering principles: **Zero Hallucinations**—every single data point originates from a legitimate web source URL with complete provenance—and strict **24-hour freshness verification** for fast-moving jobs and news."*

### 2. Architecture & Technical Design (1:00 - 3:30)
> *(Open `docs/architecture.pdf` on screen)*
>
> *"Let's look at the architectural flow:
> 1. **Dual Crawling Engines:** We use `aiohttp` for high-throughput async HTTP requests and `Playwright` for headless browser rendering of JavaScript-heavy Single Page Applications.
> 2. **Polite Anti-Bot Resiliency:** We enforce bounded concurrency using per-source semaphores, per-source rate limits, and exponential backoff with full jitter, honoring `Retry-After` headers.
> 3. **413 Payload Too Large Prevention:** Before any data reaches downstream processing, our HTML cleaner strips out boilerplates, scripts, navigation, footers, and styles, retaining pure semantic text.
> 4. **Deterministic Metadata & Date Parsing:** Dates are parsed through a multi-tier hierarchy: JSON-LD schemas first, then OpenGraph tags, `<time>` tags, and regex, standardizing everything into timezone-aware UTC ISO-8601 timestamps.
> 5. **Deterministic GitHub Stars:** For research papers, star counts are pulled directly and deterministically from GitHub's REST API—never guessed by an LLM.
> 6. **Entity Resolution:** Messy company variations (like 'OpenAI, Inc.' vs 'OpenAI') are canonicalized using rule-based algorithms with an immutable audit log.
> 7. **Storage & Cloud Delivery:** We persist records to PostgreSQL 16 using `asyncpg` with idempotent upsert queries on `source_url`, and sync directly to Google Sheets."*

### 3. Live Pipeline Demonstration (3:30 - 6:00)
> *(Switch to Terminal in VS Code)*
>
> *"Let's see the system in action.*
>
> *First, we verify the infrastructure health:*
> ```bash
> python -m src.main health
> ```
> *(Show healthy PostgreSQL and Redis connections)*
>
> *Next, we can run a dry-run to verify crawler routing without writing to the database:*
> ```bash
> python -m src.main run --dry-run
> ```
> *(Show the 18 sources being processed safely)*
>
> *And our pipeline runner ingests live sources and exports them directly into PostgreSQL and Google Sheets:*
> ```bash
> python -m scripts.ingest_and_export_live_data
> ```
> *(Point out live output: GitHub stars fetched dynamically for DeepSeek-V3, LLaMA, Whisper, etc., and database upserts)*"

### 4. Data Output — Google Sheets Walkthrough (6:00 - 8:00)
> *(Open the Google Sheet on browser: `https://docs.google.com/spreadsheets/d/1-0idPMCMKrK0bAzdAPzf8v6LbfIHiIZOxscJ_etX9p0/edit`)*
>
> *"Now let's inspect the synchronized Google Sheet output across all required tabs:
> - **Startups Tab:** Contains verified startup records from Y Combinator and Techstars with founding dates, descriptions, official websites, and origin URLs.
> - **Products Tab:** Contains AI tools (ChatGPT, Claude 3.5 Sonnet, Cursor, Perplexity, Midjourney) with categories and pricing models.
> - **Research Papers Tab:** Notice the ArXiv links and verified GitHub star counts retrieved deterministically from GitHub (e.g. DeepSeek-V3 with >100,000 stars, Whisper with >108,000 stars).
> - **Jobs Tab:** AI roles from Work at a Startup, RemoteOK, and AIJobs, all strictly within the 24-hour freshness window.
> - **News Tab:** Breaking news stories with full provenance and verified publication dates.
> - **Entity Mapping Log Tab:** Full audit trail showing raw input names, canonicalized names, matching methods, and confidence scores."*

### 5. Test Suite & Code Quality (8:00 - 9:00)
> *(Switch back to Terminal)*
>
> *"To ensure reliability, the codebase is backed by rigorous automated testing:*
> ```bash
> pytest
> ```
> *(Show 229 passing tests across unit, integration, and orchestration)*
>
> *We also enforce strict linting and type analysis:*
> ```bash
> ruff check .
> mypy src
> ```
> *(Show zero lint errors and zero type issues across all 58 source files)*"

### 6. Conclusion (9:00 - 9:30)
> *"In summary, the pipeline delivers a robust, scalable, zero-hallucination solution for AI ecosystem data ingestion, meeting every criteria from architecture and resilience to live persistence and cloud reporting. All code, configuration, and documentation are committed and pushed to GitHub.*
>
> *Thank you!"*
