"""Background worker for phone number reputation updates."""

from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.phone_number import PhoneNumber
from app.services.rate_limiting.reputation_tracker import ReputationTracker
from app.services.rate_limiting.warming_scheduler import WarmingScheduler
from app.workers.base import BaseWorker


class ReputationWorker(BaseWorker):
    """Background worker for phone number reputation management.

    Periodically:
    - Updates reputation metrics for all active phone numbers
    - Advances warming stages for numbers in warming
    - Logs quarantine events for alerting
    """

    POLL_INTERVAL_SECONDS = getattr(settings, "reputation_poll_interval", 300)
    COMPONENT_NAME = "reputation_worker"

    def __init__(self) -> None:
        super().__init__()
        self.tracker = ReputationTracker()
        self.warming = WarmingScheduler()

    async def _process_items(self) -> None:
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


# Global worker instance (kept for backward compatibility with main.py)
# main.py uses: from app.workers.reputation_worker import reputation_worker
# main.py calls: await reputation_worker.start()
reputation_worker = ReputationWorker()
