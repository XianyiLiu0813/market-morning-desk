"""Retry helpers with exponential backoff for flaky network calls (Section 33)."""
from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, Tuple, Type, TypeVar

T = TypeVar("T")

logger = logging.getLogger("morning_desk")


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: retry a function on exception with exponential backoff.

    Designed so ONE provider failing does not crash the whole pipeline -
    callers should still wrap the call site in try/except to degrade
    gracefully (see collectors/*.py), this decorator just avoids treating a
    transient network blip as a hard failure.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception = RuntimeError("unreachable")
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt == max_attempts:
                        logger.warning(
                            "%s failed after %d attempts: %s", func.__name__, attempt, exc
                        )
                        raise
                    logger.info(
                        "%s attempt %d/%d failed (%s), retrying in %.1fs",
                        func.__name__,
                        attempt,
                        max_attempts,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)
            raise last_exc

        return wrapper

    return decorator
