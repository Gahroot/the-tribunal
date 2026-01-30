"""Base worker class and registry for background workers.

Provides a reusable base class that extracts common worker patterns:
- Start/stop lifecycle management
- Async run loop with configurable poll interval
- Logging with component name binding
- Singleton registry for global worker instances
"""

import asyncio
import contextlib
from abc import ABC, abstractmethod
from typing import ClassVar

import structlog

logger = structlog.get_logger()


class BaseWorker(ABC):
    """Abstract base class for background workers.

    Subclasses must implement:
    - _process_items(): Main processing logic called each poll cycle

    Subclasses may optionally implement:
    - _on_start(): Called before the run loop starts (setup resources)
    - _on_stop(): Called after the run loop stops (cleanup resources)

    Class attributes:
    - POLL_INTERVAL_SECONDS: Time between poll cycles (default: 60)
    - COMPONENT_NAME: Logger component name (default: class name lowercase)

    Example:
        class MyWorker(BaseWorker):
            POLL_INTERVAL_SECONDS = 30
            COMPONENT_NAME = "my_worker"

            async def _process_items(self) -> None:
                # Do work each cycle
                pass
    """

    POLL_INTERVAL_SECONDS: ClassVar[int] = 60
    COMPONENT_NAME: ClassVar[str | None] = None

    def __init__(self, poll_interval: int | None = None) -> None:
        """Initialize the worker.

        Args:
            poll_interval: Optional override for poll interval in seconds.
        """
        self.running = False
        self._task: asyncio.Task[None] | None = None
        self._poll_interval = poll_interval or self.POLL_INTERVAL_SECONDS
        self.logger = logger.bind(
            component=self.COMPONENT_NAME or self.__class__.__name__.lower()
        )

    async def start(self) -> None:
        """Start the worker background task."""
        if self.running:
            self.logger.warning("Worker already running")
            return

        self.running = True
        await self._on_start()
        self._task = asyncio.create_task(self._run_loop())
        self.logger.info("Worker started")

    async def stop(self) -> None:
        """Stop the worker."""
        self.running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._on_stop()
        self.logger.info("Worker stopped")

    async def _run_loop(self) -> None:
        """Main worker loop that polls for items to process."""
        while self.running:
            try:
                await self._process_items()
            except Exception:
                self.logger.exception("Error in worker loop")

            await asyncio.sleep(self._poll_interval)

    @abstractmethod
    async def _process_items(self) -> None:
        """Process items in a single poll cycle.

        Subclasses must implement this method with their specific logic.
        """

    async def _on_start(self) -> None:  # noqa: B027
        """Hook called before the run loop starts.

        Override to initialize resources (e.g., HTTP clients, services).
        """

    async def _on_stop(self) -> None:  # noqa: B027
        """Hook called after the run loop stops.

        Override to clean up resources (e.g., close HTTP clients).
        """


class WorkerRegistry[W: BaseWorker]:
    """Manages singleton lifecycle for a worker class.

    Provides start/stop/get functions that maintain a single global instance
    of a worker type.

    Example:
        _registry = WorkerRegistry(MyWorker)
        start_my_worker = _registry.start
        stop_my_worker = _registry.stop
        get_my_worker = _registry.get
    """

    def __init__(self, worker_class: type[W]) -> None:
        """Initialize the registry.

        Args:
            worker_class: The worker class to manage.
        """
        self._worker_class = worker_class
        self._instance: W | None = None

    async def start(self) -> W:
        """Start the global worker instance.

        Creates a new instance if none exists and starts it.

        Returns:
            The running worker instance.
        """
        if self._instance is None:
            self._instance = self._worker_class()
            await self._instance.start()
        return self._instance

    async def stop(self) -> None:
        """Stop and clear the global worker instance."""
        if self._instance:
            await self._instance.stop()
            self._instance = None

    def get(self) -> W | None:
        """Get the current worker instance.

        Returns:
            The worker instance if running, None otherwise.
        """
        return self._instance
