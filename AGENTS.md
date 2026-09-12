# AI Intelligence Pipeline — Agent Instructions

## Project Goal

Build the AI Engineer demo task described in `assignment.md`.

The system must demonstrate a production-oriented, scalable, fault-tolerant ingestion pipeline for:

* Startups
* Products
* Research papers
* AI jobs
* AI news

The system must prioritize data quality, provenance, resilience, scalability, and maintainability.

---

# NON-NEGOTIABLE RULES

## 1. Never hallucinate data

The LLM must NEVER be treated as a source of truth.

Every factual record must originate from a legitimate source URL.

If information cannot be reliably extracted:

* use null where the schema allows it
* mark the extraction as uncertain
* or send the record to quarantine

Never invent values.

---

## 2. Preserve provenance

Every extracted record must retain:

* source URL
* source name
* collection timestamp
* raw document reference where practical
* extraction status

A reviewer must be able to trace a final record back to its source.

---

## 3. Preserve raw data

Never overwrite raw source information with canonicalized information.

Where entity resolution occurs, preserve both:

* raw name
* canonical name

Example:

raw_name:
"OpenAI, Inc."

canonical_name:
"OpenAI"

---

## 4. Use deterministic logic whenever possible

Use normal code for:

* URL normalization
* deduplication
* date parsing
* freshness calculation
* GitHub star retrieval
* schema validation
* HTTP status handling
* retries
* concurrency control

Use LLMs for tasks that actually require language understanding.

---

# Technology

Use Python 3.12+.

Preferred technologies:

* aiohttp
* asyncio
* Playwright
* BeautifulSoup
* lxml
* trafilatura
* Pydantic
* PostgreSQL
* Redis
* pytest
* pytest-asyncio
* Ruff
* mypy

Use additional dependencies only when justified.

---

# Architecture

The logical pipeline is:

Sources
→ Async Crawlers
→ Raw Document
→ URL Deduplication
→ HTML Cleaning
→ Date Extraction
→ Freshness Filtering
→ Intelligent Chunking
→ LLM Extraction
→ Pydantic Validation
→ Entity Resolution
→ Final Validation
→ PostgreSQL
→ Export

---

# Async Requirements

Network operations must be asynchronous where practical.

Use:

* aiohttp for normal HTTP
* Playwright async for JavaScript-heavy pages

Use bounded concurrency.

Never create an unbounded number of simultaneous requests.

Do not use blocking network operations inside async workers.

---

# Retry Requirements

Implement exponential backoff with jitter.

Retry transient failures such as:

* 408
* 429
* 500
* 502
* 503
* 504
* network timeouts
* temporary connection failures

Do not blindly retry permanent failures such as:

* 400
* 401
* 403
* 404

Respect `Retry-After` where available.

---

# LLM Requirements

Implement an abstraction around LLM providers.

Preferred fallback order:

1. Gemini
2. Groq
3. DeepSeek

The rest of the application must not depend directly on a specific provider.

The LLM layer must support:

* retries
* exponential backoff
* jitter
* provider fallback
* structured output
* validation
* token/context limits
* logging

---

# 413 Handling

Never send arbitrarily large documents to an LLM.

Before extraction:

1. Remove irrelevant HTML.
2. Extract meaningful content.
3. Estimate payload size/token count.
4. Chunk large documents.
5. Preserve semantically important sections.
6. Extract structured information from chunks where necessary.

Never solve 413 errors by simply increasing limits or blindly truncating the beginning of a document.

---

# 429 Handling

Handle rate limiting explicitly.

Use:

* bounded concurrency
* provider-specific rate limits
* exponential backoff
* jitter
* Retry-After
* provider fallback

Do not create retry storms.

---

# Freshness Requirements

News and jobs must satisfy the assignment's 24-hour freshness requirement.

Date extraction priority should generally be:

1. JSON-LD
2. OpenGraph/meta tags
3. `<time>` elements
4. visible page dates
5. relative dates
6. source-specific logic
7. carefully documented heuristic

Normalize all dates to timezone-aware ISO-8601 timestamps.

Do not guess publication dates.

---

# Entity Resolution

Entity resolution must canonicalize messy names.

Examples:

"Open AI"
"OpenAI Inc."
"OpenAI, Inc."
"OPENAI"

→

"OpenAI"

Maintain an entity mapping log containing:

* raw name
* canonical name
* matching method
* confidence where appropriate
* source

---

# Deduplication

Normalize URLs before deduplication.

Remove irrelevant tracking parameters where safe.

Use stable identifiers/hashes.

Prevent duplicate processing across workers.

Design the system so distributed workers cannot accidentally process the same source simultaneously.

---

# Research Papers

Research papers must include:

* title
* authors
* paper URL
* GitHub URL where available
* current GitHub stars
* publication date

GitHub star counts must come from GitHub or another legitimate deterministic source, not from LLM guesses.

---

# Database

Use PostgreSQL as the primary system of record.

Design tables for:

* raw_documents
* startups
* products
* research_papers
* jobs
* news
* entity_mappings
* crawl_runs
* extraction_runs
* quarantined_records

Use appropriate indexes and unique constraints.

---

# Google Sheets

Google Sheets is an output destination, not the primary database.

Export validated records to:

1. Startups
2. Products
3. Research Papers
4. Jobs
5. News
6. Entity Mapping Log

---

# Error Handling

Do not silently swallow exceptions.

Failures must contain enough information to debug:

* URL
* source
* pipeline stage
* error type
* timestamp
* retry count
* provider where applicable

Use structured logging.

---

# Testing

Every important component must have tests.

At minimum test:

* URL normalization
* deduplication
* date parsing
* relative date parsing
* 24-hour freshness
* entity resolution
* schema validation
* chunking
* retry behavior
* 429 fallback
* invalid LLM output
* concurrency limits

---

# Code Quality

Prefer:

* small functions
* clear interfaces
* type hints
* dependency injection where useful
* configuration instead of hardcoded values
* reusable abstractions
* meaningful names

Avoid:

* giant functions
* duplicated provider logic
* hardcoded API keys
* magic numbers
* unnecessary frameworks
* unnecessary dependencies

---

# Secrets

Never hardcode credentials.

Use environment variables.

Provide `.env.example`.

Never commit `.env`.

---

# Development Strategy

Implement incrementally.

Do NOT build the entire system in one step.

After every major feature:

1. Run tests.
2. Run linting.
3. Run type checks where configured.
4. Inspect for regressions.
5. Report what changed.
6. Report remaining issues.

Do not make unrelated changes.

---

# Important Agent Behavior

Before implementing a major feature:

* inspect the existing code
* understand existing abstractions
* reuse existing components
* avoid duplicating functionality

If requirements are ambiguous:

* choose a reasonable engineering solution
* document the decision
* do not fabricate requirements

The final implementation must remain understandable to a human engineer.
