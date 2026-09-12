"""Retry utilities with exponential backoff, jitter, and Retry-After support."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TypeVar

from src.utils.logging import get_logger

logger = get_logger(__name__)

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})
PERMANENT_STATUS_CODES: frozenset[int] = frozenset({400, 401, 403, 404})

T = TypeVar("T")


class MaxRetriesExceededError(Exception):
    """Raised when an operation fails after exhausting all retry attempts."""

    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        attempts: int = 0,
        last_status: int | None = None,
        last_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.attempts = attempts
        self.last_status = last_status
        self.last_error = last_error


class PermanentHttpError(Exception):
    """Raised for non-retryable HTTP client errors (400, 401, 403, 404)."""

    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        status: int = 0,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.status = status


def parse_retry_after(header_value: str | None) -> float | None:
    """Parse a Retry-After HTTP header value into seconds.

    Supports both integer seconds (e.g., '120') and HTTP-date strings
    (e.g., 'Wed, 21 Oct 2026 07:28:00 GMT').

    Args:
        header_value: Value of the Retry-After header.

    Returns:
        Number of seconds to wait, or None if invalid/missing.
    """
    if not header_value:
        return None
    val = header_value.strip()
    if not val:
        return None

    # Try numeric seconds
    try:
        seconds = float(val)
        return max(0.0, seconds)
    except ValueError:
        pass

    # Try HTTP date
    try:
        target_dt = parsedate_to_datetime(val)
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=UTC)
        now_dt = datetime.now(UTC)
        diff = (target_dt - now_dt).total_seconds()
        return max(0.0, diff)
    except (ValueError, TypeError):  # Preserve original behavior but specify exception type
        # Optional: log exception if needed
        return None


def is_retryable_status(status: int) -> bool:
    """Determine whether an HTTP status code is retryable."""
    return status in RETRYABLE_STATUS_CODES


def is_permanent_status(status: int) -> bool:
    """Determine whether an HTTP status code is permanently non-retryable."""
    return status in PERMANENT_STATUS_CODES


@dataclass
class RetryConfig:
    """Configuration for exponential backoff and retries."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_factor: float = 2.0
    jitter: bool = True
    retryable_statuses: frozenset[int] = field(default_factory=lambda: RETRYABLE_STATUS_CODES)


def calculate_backoff(
    attempt: int,
    config: RetryConfig,
    retry_after: float | None = None,
) -> float:
    """Calculate the backoff duration with exponential backoff and jitter.

    If a valid Retry-After value is supplied, it is respected as the minimum wait time.

    Args:
        attempt: Zero-based retry attempt number (0, 1, 2, ...).
        config: Retry configuration.
        retry_after: Optional explicit seconds from Retry-After header.

    Returns:
        Computed delay in seconds.
    """
    if retry_after is not None and retry_after > 0:
        # Honor Retry-After header with a small jitter if enabled
        if config.jitter:
            return min(config.max_delay, retry_after + random.uniform(0.0, 0.5))
        return min(config.max_delay, retry_after)

    # Standard exponential backoff: base_delay * factor^attempt
    delay = config.base_delay * (config.exponential_factor**attempt)
    capped_delay = min(config.max_delay, delay)

    if config.jitter:
        # Full jitter between 50% and 100% of capped delay
        return random.uniform(capped_delay * 0.5, capped_delay)

    return capped_delay


async def execute_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    config: RetryConfig,
    url: str,
    status_extractor: Callable[[T], int | None] | None = None,
    retry_after_extractor: Callable[[T], float | None] | None = None,
) -> T:
    """Execute an asynchronous operation with retry logic.

    Args:
        operation: Async callable returning a result.
        config: Retry configuration.
        url: Request URL for logging and error reporting.
        status_extractor: Optional callable to extract HTTP status from the result.
        retry_after_extractor: Optional callable to extract Retry-After seconds.

    Returns:
        The result of the operation if successful.

    Raises:
        PermanentHttpError: If a permanent client error (400, 401, 403, 404) is received.
        MaxRetriesExceededError: If max retries are exceeded for transient errors.
        Exception: Any other fatal unhandled exception.
    """
    last_error: Exception | None = None
    last_status: int | None = None

    for attempt in range(config.max_retries + 1):
        try:
            result = await operation()

            if status_extractor is not None:
                status = status_extractor(result)
                if status is not None:
                    last_status = status
                    if is_permanent_status(status):
                        logger.warning(
                            "permanent_http_error_no_retry",
                            url=url,
                            status=status,
                            attempt=attempt,
                        )
                        raise PermanentHttpError(
                            f"HTTP {status} permanent failure for {url}",
                            url=url,
                            status=status,
                        )

                    if is_retryable_status(status):
                        if attempt >= config.max_retries:
                            logger.error(
                                "max_retries_exceeded_status",
                                url=url,
                                status=status,
                                attempts=attempt + 1,
                            )
                            raise MaxRetriesExceededError(
                                f"Max retries ({config.max_retries}) exceeded for {url} with status {status}",
                                url=url,
                                attempts=attempt + 1,
                                last_status=status,
                            )

                        retry_after = (
                            retry_after_extractor(result)
                            if retry_after_extractor is not None
                            else None
                        )
                        delay = calculate_backoff(attempt, config, retry_after)
                        logger.warning(
                            "retrying_transient_status",
                            url=url,
                            status=status,
                            attempt=attempt + 1,
                            delay_seconds=round(delay, 2),
                            retry_after=retry_after,
                        )
                        await asyncio.sleep(delay)
                        continue

            return result

        except PermanentHttpError:
            raise
        except MaxRetriesExceededError:
            raise
        except Exception as exc:

            if attempt >= config.max_retries:
                logger.error(
                    "max_retries_exceeded_exception",
                    url=url,
                    attempt=attempt + 1,
                    exception=str(exc),
                )
                raise MaxRetriesExceededError(
                    f"Max retries ({config.max_retries}) exceeded for {url}: {exc}",
                    url=url,
                    attempts=attempt + 1,
                    last_status=last_status,
                    last_error=exc,
                ) from exc

            delay = calculate_backoff(attempt, config)
            logger.warning(
                "retrying_after_exception",
                url=url,
                attempt=attempt + 1,
                delay_seconds=round(delay, 2),
                exception_type=type(exc).__name__,
                exception=str(exc),
            )
            await asyncio.sleep(delay)

    # Should not be reachable, but safeguard
    raise MaxRetriesExceededError(
        f"Retries exhausted for {url}",
        url=url,
        attempts=config.max_retries + 1,
        last_status=last_status,
        last_error=last_error,
    )
