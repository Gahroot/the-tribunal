"""Retryable worker mixin — exponential backoff with jitter for transient failures.

Provides `RetryableWorker`, a mixin intended to be combined with `BaseWorker`
(or used standalone by any class exposing a bound `self.logger`). Wrap
per-item processing in `execute_with_retry` so transient errors are retried
with exponential backoff and jittered sleeps. Terminal failures are sent to
`_dead_letter`, which currently only logs — a Redis-backed DLQ can be layered
on later without changing call sites.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, TypeVar

import structlog

logger = structlog.get_logger()

T = TypeVar("T")


class RetryableWorker:
    """Mixin that adds exponential-backoff retries to a worker.

    Class attributes:
    - max_retries: Maximum retry attempts after the initial call (default: 3).
      A value of 3 means up to 4 total attempts.
    - backoff_base_seconds: Base delay for exponential backoff (default: 2.0).
      Delay for attempt N is `base * 2**N` plus uniform jitter in [0, base).

    Example:
        class MyWorker(RetryableWorker, BaseWorker):
            max_retries = 5

            async def _process_items(self) -> None:
                for item in items:
                    await self.execute_with_retry(self._handle, item)
    """

    max_retries: ClassVar[int] = 3
    backoff_base_seconds: ClassVar[float] = 2.0

    logger: Any  # Provided by BaseWorker or similar host class.

    async def execute_with_retry(
        self,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T | None:
        """Invoke `fn(*args, **kwargs)` with exponential backoff on failure.

        Returns the function's result on success, or `None` after all retries
        are exhausted (the terminal exception is forwarded to `_dead_letter`).
        """
        attempt = 0
        last_exc: BaseException | None = None
        while attempt <= self.max_retries:
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                delay = self.backoff_base_seconds * (2**attempt) + random.uniform(
                    0, self.backoff_base_seconds
                )
                self.logger.warning(
                    "Retryable error, backing off",
                    fn=getattr(fn, "__name__", repr(fn)),
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    delay_seconds=round(delay, 3),
                    error=str(exc),
                )
                await asyncio.sleep(delay)
                attempt += 1

        await self._dead_letter(fn, args, kwargs, last_exc)
        return None

    async def _dead_letter(
        self,
        fn: Callable[..., Awaitable[Any]],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        exc: BaseException | None,
    ) -> None:
        """Record a permanently failed task.

        Default implementation logs via the host's structlog logger. Override
        to push to a Redis DLQ, database table, or alerting pipeline.
        """
        self.logger.error(
            "Dead letter: retries exhausted",
            fn=getattr(fn, "__name__", repr(fn)),
            args=repr(args),
            kwargs=repr(kwargs),
            error=str(exc) if exc else None,
            exc_info=exc,
        )
