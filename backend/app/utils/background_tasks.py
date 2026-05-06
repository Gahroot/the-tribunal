"""Safe fire-and-forget asyncio task helper.

Per the Python 3.11+ docs for :func:`asyncio.create_task`:

    Important: Save a reference to the result of this function, to avoid
    a task disappearing mid-execution. The event loop only keeps weak
    references to tasks. A task that isn't referenced elsewhere may be
    garbage collected at any time, even before it's done.

This module exposes :func:`spawn_background_task`, which:

1. Pins the task in a module-level ``set`` so the GC can't collect it.
2. Removes it from the set on completion (preventing a memory leak).
3. Logs unhandled exceptions via ``structlog`` so failures aren't silent.

Usage::

    from app.utils.background_tasks import spawn_background_task

    spawn_background_task(
        send_email(...),
        name="appointment_booked_email",
    )
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog

logger = structlog.get_logger()

# Module-level strong references to in-flight background tasks. Without this,
# the event loop's weak reference is the only handle and the GC may silently
# cancel tasks before they finish.
_background_tasks: set[asyncio.Task[Any]] = set()


def _log_task_exception(task: asyncio.Task[Any]) -> None:
    """Log unhandled exceptions from a completed background task.

    ``CancelledError`` is intentionally swallowed (cancellation is not a
    failure). Any other exception is logged with the task name so it
    surfaces in production logs instead of being silently dropped.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is None:
        return
    logger.error(
        "background_task_failed",
        task_name=task.get_name(),
        error=str(exc),
        error_type=type(exc).__name__,
        exc_info=exc,
    )


def spawn_background_task(
    coro: Coroutine[Any, Any, Any],
    *,
    name: str | None = None,
) -> asyncio.Task[Any]:
    """Schedule a fire-and-forget coroutine with safe lifecycle handling.

    Args:
        coro: The coroutine to run in the background.
        name: Optional task name (surfaces in logs and ``asyncio`` debug output).

    Returns:
        The created :class:`asyncio.Task`. Callers usually ignore it; the
        helper retains a strong reference internally until completion.
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(_log_task_exception)
    return task


def background_task_count() -> int:
    """Return the number of in-flight background tasks (for diagnostics)."""
    return len(_background_tasks)
