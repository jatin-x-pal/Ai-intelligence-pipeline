# Crawling Strategy (Phase V)

## Overview
The AI Intelligence Pipeline ingests data from a diverse set of web sources (start‑ups, products, research papers, AI jobs, AI news).  To guarantee **scalability**, **fault‑tolerance**, and **compliance** with target‑site policies, the crawler layer is split into two deterministic implementations:

- **HTTP Crawler** – lightweight, asynchronous `aiohttp`‑based fetcher for plain HTML pages.
- **Browser Crawler** – async Playwright (Chromium) runner for JavaScript‑heavy pages.

Both crawlers share a common contract defined in `src.crawlers.base.BaseCrawler` and are orchestrated by `src.crawlers.pipeline.SourceCrawlPipeline`.

## Key Design Goals
1. **Bounded Concurrency** – each source can configure `max_concurrency` (a semaphore) to limit the number of simultaneous requests.
2. **Per‑Source Rate Limiting** – optional `rate_limit_per_second` guarantees a minimum interval between requests to the same host.
3. **Robust Retry Logic** – transient HTTP errors (`408, 429, 5xx, network‑timeouts`) trigger exponential back‑off with jitter.  `Retry‑After` headers are honoured when present.
4. **Graceful Block Handling** – permanent failures (`400, 401, 403, 404`) are captured as `PermanentHttpError` and the source is **quarantined** rather than retried indefinitely.
5. **Timeouts & Isolation** – each request respects a configurable `timeout_seconds`.  Browser sessions are created per‑source and torn down after use to avoid state leakage.

## Crawler Selection
The decision is deterministic and sourced from `config/sources.yaml` via the `crawl_method` field:

| Method | Implementation | Typical Use‑Case |
|--------|----------------|-----------------|
| `HTTP` | `HttpCrawler` (aiohttp) | Static pages, API endpoints, RSS feeds |
| `BROWSER` | `BrowserCrawler` (Playwright) | Pages that require JavaScript rendering, infinite scroll, or dynamic content |

The pipeline’s private helper `_choose_crawler` (in `SourceCrawlPipeline`) simply returns the appropriate class based on this enum – no heuristic or LLM‑based guessing is performed.

## Retry & Back‑off Algorithm
```python
# Simplified pseudo‑code (see src.utils.retry)
await asyncio.sleep(base * (2 ** attempt) + random.uniform(0, jitter))
```
- **Base** = 0.5 s, **Jitter** = 0.25 s.
- The algorithm caps at `max_retries` (default 5) and respects any `Retry‑After` header returned by the server.

## Permanent‑Error Detection
`src.crawlers.base.is_permanent_status` returns `True` for status codes that **must not** be retried.  When a permanent error is encountered the pipeline records the failure, attaches the HTTP status to the `CrawledDocument`, and marks the source as *quarantined* (the downstream reviewer can later re‑enable it).

## Configuration Example (`config/sources.yaml`)
```yaml
- name: "OpenAI Blog"
  category: news
  crawl_method: HTTP
  base_url: "https://openai.com/blog/"
  enabled: true
  max_concurrency: 3
  rate_limit_per_second: 2   # ≤ 2 requests per second
  timeout_seconds: 15
  headers:
    User-Agent: "AI‑Intelligence‑Pipeline/1.0"
```
All fields map directly to attributes on `SourceConfig` and are consumed by the pipeline without any additional runtime logic.

## Monitoring & Observability
- **Structured logging** (`src.utils.logging`) records each request with `source`, `url`, `status`, `latency_ms`, and `error` (if any).
- The pipeline returns a `CrawledDocument` that includes `status_code`, `is_success`, `error`, and provenance fields (`source_name`, `collected_at`, `normalized_url`).

## Future Extensibility
The strategy is deliberately versioned via this document.  Adding new crawler types (e.g., a headless `FirefoxCrawler`) only requires:
1. Implementing `BaseCrawler`.
2. Adding a new enum entry to `CrawlMethod`.
3. Updating the `SourceCrawlPipeline.get_crawler_for_source` mapping.
All existing sources continue to function unchanged because the selection is **explicit** in the YAML configuration.

---
*This document is part of the repository’s official documentation and should be kept in sync with any changes to the crawler implementation.*
