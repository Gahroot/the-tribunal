"""Connection resilience utilities for voice agents.

This module provides retry logic and circuit breaker patterns for
production-grade reliability in voice agent connections.

Features:
- Exponential backoff retry decorator
- Circuit breaker to prevent cascade failures
- Health check protocol

Usage:
    @with_retry(max_attempts=3, base_delay=1.0)
    async def connect_to_provider():
        ...

    breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
    async with breaker:
        await risky_operation()
"""

import asyncio
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import structlog

from app.services.ai.exceptions import (
    VoiceAgentConnectionError,
    VoiceAgentTimeoutError,
)

logger = structlog.get_logger()

P = ParamSpec("P")
T = TypeVar("T")


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator for retry with exponential backoff.

    Retries the decorated function on failure with exponential backoff
    between attempts. Useful for transient network failures.

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 30.0)
        exponential_base: Base for exponential backoff (default: 2.0)
        retryable_exceptions: Tuple of exceptions to retry on
            (default: ConnectionError, TimeoutError, OSError)

    Returns:
        Decorator function

    Example:
        @with_retry(max_attempts=3, base_delay=1.0)
        async def connect():
            return await websocket.connect(url)
    """
    if retryable_exceptions is None:
        retryable_exceptions = (
            ConnectionError,
            TimeoutError,
            OSError,
            VoiceAgentConnectionError,
            VoiceAgentTimeoutError,
        )

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            log = logger.bind(function=func.__name__)
            last_exception: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)  # type: ignore[misc, no-any-return]
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        # Calculate delay with exponential backoff
                        delay = min(
                            base_delay * (exponential_base ** (attempt - 1)),
                            max_delay,
                        )
                        log.warning(
                            "retry_after_failure",
                            attempt=attempt,
                            max_attempts=max_attempts,
                            delay_seconds=delay,
                            error=str(e),
                            error_type=type(e).__name__,
                        )
                        await asyncio.sleep(delay)
                    else:
                        log.error(
                            "max_retries_exceeded",
                            attempts=max_attempts,
                            error=str(e),
                            error_type=type(e).__name__,
                        )

            # All attempts failed
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper  # type: ignore[return-value]

    return decorator


class CircuitBreaker:
    """Circuit breaker for preventing cascade failures.

    Tracks failures and opens the circuit when threshold is exceeded,
    preventing further calls until recovery timeout elapses.

    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Circuit tripped, calls fail immediately
    - HALF_OPEN: Testing recovery, limited calls allowed

    Attributes:
        failure_threshold: Failures before opening circuit
        recovery_timeout: Seconds before attempting recovery
        state: Current circuit state
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        name: str = "circuit_breaker",
    ) -> None:
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening
            recovery_timeout: Seconds to wait before recovery attempt
            name: Name for logging
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name
        self.logger = logger.bind(circuit_breaker=name)

        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        """Get current circuit state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == self.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (failing fast)."""
        return self._state == self.OPEN

    async def _should_attempt(self) -> bool:
        """Check if a call should be attempted.

        Returns:
            True if call should proceed
        """
        async with self._lock:
            if self._state == self.CLOSED:
                return True

            if self._state == self.OPEN:
                # Check if recovery timeout has elapsed
                if self._last_failure_time is not None:
                    elapsed = time.time() - self._last_failure_time
                    if elapsed >= self.recovery_timeout:
                        self._state = self.HALF_OPEN
                        self.logger.info(
                            "circuit_entering_half_open",
                            elapsed_seconds=elapsed,
                        )
                        return True
                return False

            # HALF_OPEN: allow attempt
            return True

    async def record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            if self._state == self.HALF_OPEN:
                self._state = self.CLOSED
                self._failure_count = 0
                self.logger.info("circuit_closed_after_success")
            elif self._state == self.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == self.HALF_OPEN:
                # Failed during recovery test - reopen circuit
                self._state = self.OPEN
                self.logger.warning("circuit_reopened_after_half_open_failure")

            elif self._state == self.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = self.OPEN
                    self.logger.warning(
                        "circuit_opened",
                        failure_count=self._failure_count,
                        threshold=self.failure_threshold,
                    )

    async def __aenter__(self) -> "CircuitBreaker":
        """Context manager entry - check if call should proceed."""
        if not await self._should_attempt():
            raise VoiceAgentConnectionError(
                "Circuit breaker is open - service temporarily unavailable",
                provider=self.name,
            )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """Context manager exit - record success or failure."""
        if exc_type is None:
            await self.record_success()
        else:
            await self.record_failure()
        return False  # Don't suppress exceptions

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self.logger.info("circuit_reset")


class ConnectionPool:
    """Simple connection health tracking for voice providers.

    Tracks connection health across multiple call attempts to
    identify systemic issues.

    Attributes:
        provider: Provider name for logging
        max_tracked: Maximum connections to track
    """

    def __init__(
        self,
        provider: str,
        max_tracked: int = 100,
    ) -> None:
        """Initialize connection pool tracker.

        Args:
            provider: Provider name
            max_tracked: Maximum connection history to keep
        """
        self.provider = provider
        self.max_tracked = max_tracked
        self.logger = logger.bind(provider=provider)

        self._connection_history: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def record_connection(
        self,
        success: bool,
        latency_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        """Record a connection attempt.

        Args:
            success: Whether connection succeeded
            latency_ms: Connection latency in milliseconds
            error: Error message if failed
        """
        async with self._lock:
            self._connection_history.append({
                "timestamp": time.time(),
                "success": success,
                "latency_ms": latency_ms,
                "error": error,
            })

            # Trim history
            if len(self._connection_history) > self.max_tracked:
                self._connection_history = self._connection_history[-self.max_tracked :]

    def get_health_stats(self) -> dict[str, Any]:
        """Get connection health statistics.

        Returns:
            Dictionary with health metrics
        """
        if not self._connection_history:
            return {
                "total_connections": 0,
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
            }

        total = len(self._connection_history)
        successes = sum(1 for c in self._connection_history if c["success"])
        latencies = [c["latency_ms"] for c in self._connection_history if c["latency_ms"]]

        return {
            "total_connections": total,
            "successful_connections": successes,
            "success_rate": successes / total if total > 0 else 0.0,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "recent_errors": [
                c["error"]
                for c in self._connection_history[-5:]
                if not c["success"] and c["error"]
            ],
        }
