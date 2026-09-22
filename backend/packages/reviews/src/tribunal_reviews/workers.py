"""Background workers for the ``reviews`` block.

* ``ReviewRequestWorker`` — polls for PENDING review requests whose per-workspace
  send delay has elapsed and dispatches the review-request SMS via the shared
  :class:`ReviewService`. Keeping the actual send out of the Cal.com webhook
  means a happy customer is asked for a review a sensible interval after the job
  (configurable per workspace) rather than the instant the meeting ends.
* ``ReputationWorker`` — periodically updates phone-number reputation metrics,
  advances warming stages, and logs quarantine events for alerting. Reputation
  scoring + warming come from the compliance block's public API.

``register_workers(registry)`` is the optional block contract: it appends both
workers to a host worker registry. The module also exposes the two
``WorkerRegistry`` singletons for hosts that wire a static worker spec list.
Core worker primitives come only through ``app.core_api``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core_api import (
    AsyncSessionLocal,
    derive_worker_retry_key,
    settings,
)
from app.models.phone_number import PhoneNumber

# Cross-block public API (declared depends_on: compliance).
from app.services.rate_limiting.reputation_tracker import ReputationTracker
from app.services.rate_limiting.warming_scheduler import WarmingScheduler

# Worker runtime primitives are imported from their source modules rather than
# the ``app.core_api`` facade on purpose: the facade itself imports
# ``app.workers.base`` at module load, so when the host's worker registry imports
# this block, ``app.core_api`` is still mid-initialization and its re-exported
# ``BaseWorker``/``WorkerRegistry`` names are not yet bound. ``app.workers.base``
# and ``app.workers.retryable`` are core modules (no sibling-block coupling).
from app.workers.base import BaseWorker, WorkerRegistry
from app.workers.retryable import RetryableWorker

from .service import ReviewService

MAX_REQUESTS_PER_TICK = 20


class ReviewRequestWorker(RetryableWorker, BaseWorker):
    """Background worker that dispatches due review-request SMS."""

    POLL_INTERVAL_SECONDS = 120
    COMPONENT_NAME = "review_request_worker"
    MAX_CONCURRENCY = 5
    max_retries = 3
    backoff_base_seconds = 2.0

    async def _process_items(self) -> None:
        """Find and dispatch review requests whose delay window has elapsed."""
        async with AsyncSessionLocal() as db:
            service = ReviewService(db)
            due = await service.find_due_pending_requests(limit=MAX_REQUESTS_PER_TICK)

            if not due:
                return

            self.logger.info("dispatching_review_requests", count=len(due))

            for review_request, workspace, contact in due:
                await self.execute_with_retry(
                    service.dispatch_request,
                    workspace,
                    review_request,
                    contact,
                    item_key=derive_worker_retry_key("review_request", review_request.id),
                )
                self.record_items_processed()


class ReputationWorker(RetryableWorker, BaseWorker):
    """Background worker for phone number reputation management.

    Periodically:
    - Updates reputation metrics for all active phone numbers
    - Advances warming stages for numbers in warming
    - Logs quarantine events for alerting
    """

    POLL_INTERVAL_SECONDS = getattr(settings, "reputation_poll_interval", 300)
    COMPONENT_NAME = "reputation_worker"
    # Per-phone updates are small DB writes — modest concurrency is fine.
    MAX_CONCURRENCY = 5
    max_retries = 3
    backoff_base_seconds = 2.0

    def __init__(self) -> None:
        super().__init__()
        self.tracker = ReputationTracker()
        self.warming = WarmingScheduler()

    async def _process_items(self) -> None:
        """Update reputation for all active phone numbers."""
        async with AsyncSessionLocal() as db:
            # Get all active phone numbers
            result = await db.execute(select(PhoneNumber).where(PhoneNumber.is_active.is_(True)))
            phones = result.scalars().all()

            updated_count = 0
            warming_advanced = 0
            quarantined_count = 0

            for phone in phones:
                outcome = await self.execute_with_retry(
                    self._update_one_phone,
                    phone,
                    db,
                    item_key=f"phone:{phone.id}",
                )
                if outcome is None:
                    continue
                was_advanced, was_quarantined = outcome
                if was_quarantined:
                    quarantined_count += 1
                if was_advanced:
                    warming_advanced += 1
                updated_count += 1

            self.logger.info(
                "reputation_update_cycle_completed",
                phones_updated=updated_count,
                warming_advanced=warming_advanced,
                newly_quarantined=quarantined_count,
            )

    async def _update_one_phone(self, phone: PhoneNumber, db: AsyncSession) -> tuple[bool, bool]:
        """Update reputation for a single phone. Returns (advanced, quarantined)."""
        old_status = phone.health_status

        await self.tracker.update_phone_reputation(phone.id, db)
        await db.refresh(phone)

        was_quarantined = old_status != "quarantined" and phone.health_status == "quarantined"
        if was_quarantined:
            self.logger.warning(
                "phone_number_quarantined",
                phone_number=phone.phone_number,
                phone_number_id=str(phone.id),
                reason=phone.quarantine_reason,
            )

        was_advanced = False
        if phone.warming_stage > 0:
            was_advanced = bool(await self.warming.advance_warming_stage(phone, db))

        return was_advanced, was_quarantined


# Singleton registries (consistent with all other workers). Exposed for hosts
# that wire a static worker spec list; ``register_workers`` is the portable hook.
review_request_registry = WorkerRegistry(ReviewRequestWorker)
reputation_registry = WorkerRegistry(ReputationWorker)


def register_workers(registry: object) -> None:
    """Append this block's workers to a host worker registry.

    ``registry`` is any object with an ``add(...)`` method accepting the host's
    ``WorkerSpec`` shape (name, registry, dependencies); see
    ``app/workers/__init__.py::WorkerSpec``.
    """
    add = registry.add  # type: ignore[attr-defined]
    add(
        name="review_request_worker",
        registry=review_request_registry,
        dependencies=("postgres", "text_message_provider"),
    )
    add(
        name="reputation_worker",
        registry=reputation_registry,
        dependencies=("postgres", "redis"),
    )
