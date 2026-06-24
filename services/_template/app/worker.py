"""Background worker loop for the ``__BLOCK_ID__`` service (own process).

Mirrors the host's worker split (``app.workers.runner``) but **standalone**: this
is not one of the host's ~27 in-process workers — it runs in the service's own
process and is started by ``<block-id>-workers`` (see ``pyproject.toml``).

A stateful service (e.g. voice) runs this in a separate process when scaling the
FastAPI app, exactly as the host splits ``backend-workers`` from the API
(CLAUDE.md). A stateless service (e.g. payments) may drop it entirely.
"""

from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

import structlog

from app.config import settings

logger = structlog.get_logger()


class ServiceWorker:
    """Single-loop poll worker. Subclass and override :meth:`process_items`."""

    POLL_INTERVAL_SECONDS: int = settings.worker_poll_interval_seconds
    COMPONENT_NAME: str = f"{settings.block_id}_worker"

    async def process_items(self) -> None:
        """One poll cycle. Replace with the service's real background work."""
        logger.info("worker_tick", component=self.COMPONENT_NAME)

    async def run(self, stop_event: asyncio.Event) -> None:
        log = logger.bind(component=self.COMPONENT_NAME)
        log.info("worker_starting")
        while not stop_event.is_set():
            try:
                await self.process_items()
            except Exception:  # noqa: BLE001 — a tick failure must not kill the loop
                log.exception("worker_tick_failed")
            # Sleep, but wake immediately if shutdown is requested.
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    stop_event.wait(), timeout=self.POLL_INTERVAL_SECONDS
                )
        log.info("worker_stopped")


def _install_shutdown_handlers(stop_event: asyncio.Event) -> None:
    """Signal ``stop_event`` on SIGINT/SIGTERM (best-effort on the event loop)."""
    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
        if not stop_event.is_set():
            log = logger.bind(component=settings.block_id + "_worker")
            log.info("worker_shutdown_requested")
            stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(signum, _request_shutdown)


async def run_until_stopped() -> None:
    """Start the worker, block until stopped, then return."""
    stop_event = asyncio.Event()
    _install_shutdown_handlers(stop_event)
    await ServiceWorker().run(stop_event)


def main() -> None:
    """CLI entrypoint for ``__BLOCK_ID__-workers``."""
    asyncio.run(run_until_stopped())


if __name__ == "__main__":
    main()
