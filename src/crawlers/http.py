"""Asynchronous HTTP crawler with connection reuse, bounded concurrency, and resilient retries."""

import asyncio
from typing import Any

import aiohttp

from src.crawlers.base import BaseCrawler, CrawlResult
from src.utils.logging import get_logger
from src.utils.retry import (
    MaxRetriesExceededError,
    PermanentHttpError,
    RetryConfig,
    calculate_backoff,
    is_permanent_status,
    is_retryable_status,
    parse_retry_after,
)

logger = get_logger(__name__)


class HttpCrawler(BaseCrawler):
    """Production-grade asynchronous HTTP crawler using aiohttp."""

    def __init__(
        self,
        *,
        max_concurrency: int = 50,
        timeout: float = 30.0,
        connect_timeout: float = 10.0,
        retry_config: RetryConfig | None = None,
        default_headers: dict[str, str] | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize HTTP crawler.

        Args:
            max_concurrency: Bounded concurrency limit using Semaphore.
            timeout: Total request timeout in seconds.
            connect_timeout: Socket connect timeout in seconds.
            retry_config: Custom retry configuration (defaults to standard backoff/jitter).
            default_headers: Default headers sent on all requests.
            session: Optional pre-existing ClientSession (for DI or testing).
        """
        super().__init__(max_concurrency=max_concurrency, timeout=timeout)
        self.connect_timeout = connect_timeout
        self.retry_config = retry_config or RetryConfig()
        self.default_headers = default_headers or {
            "User-Agent": (
                "AI-Intelligence-Pipeline/1.0 "
                "(+https://github.com/frontieratlas/ai-intelligence-pipeline; bot@frontieratlas.ai)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self._session = session
        # Store ownership flag: if no external session provided, crawler owns the session and will close it.
        self._owns_session = session is None
        # No change - ownership already set above.



    async def get_session(self) -> aiohttp.ClientSession:
        """Return an active aiohttp.ClientSession, creating one if needed.

        Handles mocked sessions that may lack a ``closed`` attribute by treating them as open.
        """
        # If a session was provided (e.g., via DI for testing), reuse it.
        if self._session is not None:
            # Some mock objects may not have a ``closed`` attribute; consider them open.
            if hasattr(self._session, "closed"):
                if not self._session.closed:
                    return self._session
            else:
                return self._session
        # Otherwise, create a new session with appropriate timeout settings.
        timeout = aiohttp.ClientTimeout(total=self.timeout, connect=self.connect_timeout)
        self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def fetch(

        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        raise_for_status: bool = False,
        **kwargs: Any,
    ) -> CrawlResult:
        """Fetch a single URL with bounded concurrency, retries, and backoff.

        Args:
            url: URL to fetch.
            headers: Optional additional request headers.
            params: Optional query parameters.
            raise_for_status: If True, raise exception on HTTP 4xx/5xx errors.
            **kwargs: Extra arguments passed to session.get().

        Returns:
            A CrawlResult containing status, headers, and body.

        Raises:
            PermanentHttpError: On 400/401/403/404 if raise_for_status=True.
            MaxRetriesExceededError: When retryable errors exceed max attempts.
        """
        config = self.retry_config
        last_error: Exception | None = None
        last_status: int | None = None

        req_headers = {**self.default_headers, **(headers or {})}

        for attempt in range(config.max_retries + 1):
            session = await self.get_session()

            try:
                # Bounded concurrency: acquire semaphore only during network execution


                async with self._semaphore:
                    # Obtain the response coroutine and await it to get the response object.
                    resp_coro = session.get(
                        url, headers=req_headers, params=params, **kwargs
                    )
                    resp_obj = await resp_coro
                    async with resp_obj as resp:
                        status = resp.status
                        last_status = status
                        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                        content_type = resp.content_type
                        body = await resp.text(errors="replace")
                        # Detect simple anti-bot block pages (e.g., captcha challenges) even when status is 200
                        if status == 200:
                            lowered_body = body.lower()
                            if any(keyword in lowered_body for keyword in ("captcha", "access denied", "blocked", "challenge")):
                                logger.warning(
                                    "http_blocked_content_detected",
                                    url=url,
                                    status=status,
                                )
                                return CrawlResult(
                                    url=str(resp.url),
                                    status=status,
                                    headers=resp_headers,
                                    body=body,
                                    content_type=content_type,
                                    error="Blocked page detected",
                                )

                    status = resp.status
                    last_status = status

                    # Handle permanent non-retryable errors (400, 401, 403, 404)
                    if is_permanent_status(status):
                        logger.warning(
                            "http_permanent_error",
                            url=url,
                            status=status,
                            attempt=attempt + 1,
                        )
                        if raise_for_status:
                            raise PermanentHttpError(
                                f"Permanent HTTP {status} for {url}",
                                url=url,
                                status=status,
                            )
                        return CrawlResult(
                            url=str(resp.url),
                            status=status,
                            headers=resp_headers,
                            body=body,
                            content_type=content_type,
                            error=f"HTTP {status}",
                        )

                    # Handle retryable transient statuses (408, 429, 500, 502, 503, 504)
                    if is_retryable_status(status):
                        if attempt >= config.max_retries:
                            logger.error(
                                "http_retries_exhausted_status",
                                url=url,
                                status=status,
                                attempts=attempt + 1,
                            )
                            if raise_for_status:
                                raise MaxRetriesExceededError(
                                    f"Retries exhausted for {url} with status {status}",
                                    url=url,
                                    attempts=attempt + 1,
                                    last_status=status,
                                )
                            return CrawlResult(
                                url=str(resp.url),
                                status=status,
                                headers=resp_headers,
                                body=body,
                                content_type=content_type,
                                error=f"HTTP {status}",
                            )

                        # Extract Retry-After header if present (standard on 429/503)
                        retry_after_str = resp_headers.get("retry-after")
                        retry_after = parse_retry_after(retry_after_str)

                        delay = calculate_backoff(attempt, config, retry_after)
                        logger.warning(
                            "http_retrying_transient_status",
                            url=url,
                            status=status,
                            attempt=attempt + 1,
                            max_retries=config.max_retries,
                            delay_seconds=round(delay, 2),
                            retry_after=retry_after,
                        )
                        # Sleep outside semaphore lock
                        await asyncio.sleep(delay)
                        continue

                    # Success or unhandled non-error status (e.g. 200, 301 handled by aiohttp)
                    if raise_for_status and not (200 <= status < 300):
                        raise aiohttp.ClientResponseError(
                            request_info=resp.request_info,
                            history=resp.history,
                            status=status,
                            message=f"HTTP {status}",
                            headers=resp.headers,
                        )

                    return CrawlResult(
                        url=str(resp.url),
                        status=status,
                        headers=resp_headers,
                        body=body,
                        content_type=content_type,
                    )

            except PermanentHttpError:
                raise
            except (TimeoutError, aiohttp.ClientError, Exception) as exc:
                last_error = exc
                logger.warning(
                    "http_request_exception",
                    url=url,
                    attempt=attempt + 1,
                    max_retries=config.max_retries,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                if attempt >= config.max_retries:
                    logger.error(
                        "http_retries_exhausted_exception",
                        url=url,
                        attempts=attempt + 1,
                        exception=str(exc),
                    )
                    raise MaxRetriesExceededError(
                        f"Retries exhausted for {url}: {exc}",
                        url=url,
                        attempts=attempt + 1,
                        last_status=last_status,
                        last_error=exc,
                    ) from exc

                delay = calculate_backoff(attempt, config)
                await asyncio.sleep(delay)

        raise MaxRetriesExceededError(
            f"Retries exhausted for {url}",
            url=url,
            attempts=config.max_retries + 1,
            last_status=last_status,
            last_error=last_error,
        )

    async def close(self) -> None:
        """Close the underlying ClientSession."""
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()
            # Allow underlying connections to close cleanly
            await asyncio.sleep(0.01)
            logger.info("http_session_closed")
