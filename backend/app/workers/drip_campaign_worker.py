"""Drip campaign worker — polls every 15 minutes to advance enrollments.

Delegates all logic to drip_runner.process_active_drip_campaigns().
"""

from app.db.session import AsyncSessionLocal
from app.services.reactivation.drip_runner import process_active_drip_campaigns
from app.workers.base import BaseWorker, WorkerRegistry


class DripCampaignWorker(BaseWorker):
    """Background worker for drip campaign step advancement."""

    POLL_INTERVAL_SECONDS = 900  # 15 minutes
    COMPONENT_NAME = "drip_campaign_worker"

    async def _process_items(self) -> None:
        """Process all active drip campaigns."""
        async with AsyncSessionLocal() as db:
            await process_active_drip_campaigns(db)


# Singleton registry
_registry = WorkerRegistry(DripCampaignWorker)
start_drip_campaign_worker = _registry.start
stop_drip_campaign_worker = _registry.stop
get_drip_campaign_worker = _registry.get
