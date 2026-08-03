"""Same-provider retry-with-backoff (NFR Design pattern, Question 1 = A).

Retries only transient failures (rate limits, timeouts, 5xx) up to a configured
number of attempts with exponential backoff. Non-transient failures (auth errors,
bad requests) propagate immediately — retrying them would never succeed.
"""

import functools
import time
from collections.abc import Callable
from typing import TypeVar

from ingestion_worker.config import settings

T = TypeVar("T")


class TransientError(Exception):
    """Raised by client wrapper code to mark a failure as retry-eligible."""


def retry_with_backoff(
    max_attempts: int | None = None, base_seconds: float | None = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    attempts = max_attempts if max_attempts is not None else settings.retry_max_attempts
    base = base_seconds if base_seconds is not None else settings.retry_backoff_base_seconds

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error: TransientError | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except TransientError as exc:
                    last_error = exc
                    if attempt < attempts:
                        time.sleep(base * (2 ** (attempt - 1)))
            assert last_error is not None
            raise last_error

        return wrapper

    return decorator
