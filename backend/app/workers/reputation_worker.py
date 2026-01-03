"""Background worker for phone number reputation updates."""

import asyncio
import contextlib

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.phone_number import PhoneNumber
from app.services.rate_limiting.reputation_tracker import ReputationTracker
from app.services.rate_limiting.warming_scheduler import WarmingScheduler

logger = structlog.get_logger()

# Run reputation updates every 5 minutes
POLL_INTERVAL_SECONDS = getattr(settings, "reputation_poll_interval", 300)


class ReputationWorker:
    """Background worker for phone number reputation management.

    Periodically:
    - Updates reputation metrics for all active phone numbers
    - Advances warming stages for numbers in warming
    - Logs quarantine events for alerting
    """

    def __init__(self) -> None:
        self.running = False
        self.logger = logger.bind(component="reputation_worker")
        self._task: asyncio.Task[None] | None = None
        self.tracker = ReputationTracker()
        self.warming = WarmingScheduler()

    async def start(self) -> None:
        """Start the reputation worker."""
        if self.running:
            return

        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        self.logger.info("reputation_worker_started", interval=POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Stop the reputation worker."""
        self.running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.logger.info("reputation_worker_stopped")

    async def _run_loop(self) -> None:
        """Main worker loop."""
        while self.running:
            try:
                await self._update_all_reputations()
            except Exception:
                self.logger.exception("error_in_reputation_worker")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _update_all_reputations(self) -> None:
        """Update reputation for all active phone numbers."""
        async with AsyncSessionLocal() as db:
            # Get all active phone numbers
            result = await db.execute(
                select(PhoneNumber).where(PhoneNumber.is_active.is_(True))
            )
            phones = result.scalars().all()

            updated_count = 0
            warming_advanced = 0
            quarantined_count = 0

            for phone in phones:
                try:
                    # Capture health status before update
                    old_status = phone.health_status

                    # Update reputation metrics
                    await self.tracker.update_phone_reputation(phone.id, db)

                    # Refresh phone to get updated values
                    await db.refresh(phone)

                    # Check if number was quarantined
                    if (
                        old_status != "quarantined"
                        and phone.health_status == "quarantined"
                    ):
                        quarantined_count += 1
                        self.logger.warning(
                            "phone_number_quarantined",
                            phone_number=phone.phone_number,
                            phone_number_id=str(phone.id),
                            reason=phone.quarantine_reason,
                        )

                    # Advance warming stage if applicable
                    if phone.warming_stage > 0:
                        advanced = await self.warming.advance_warming_stage(phone, db)
                        if advanced:
                            warming_advanced += 1

                    updated_count += 1

                except Exception:
                    self.logger.exception(
                        "error_updating_phone_reputation",
                        phone_id=str(phone.id),
                    )

            self.logger.info(
                "reputation_update_cycle_completed",
                phones_updated=updated_count,
                warming_advanced=warming_advanced,
                newly_quarantined=quarantined_count,
            )


# Global worker instance
reputation_worker = ReputationWorker()
