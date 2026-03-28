"""Nudge worker — generates and delivers human-in-the-loop nudges.

Runs hourly (not every 60s like most workers — nudges are a daily concern).
For each active workspace with nudge_settings enabled:
1. NudgeGeneratorService scans contacts for upcoming dates → creates HumanNudge rows
2. NudgeDeliveryService delivers pending nudges via SMS/push to workspace members
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.workspace import Workspace
from app.services.nudges.nudge_delivery import NudgeDeliveryService
from app.services.nudges.nudge_generator import NudgeGeneratorService
from app.workers.base import BaseWorker, WorkerRegistry


class NudgeWorker(BaseWorker):
    """Background worker for generating and delivering human nudges."""

    POLL_INTERVAL_SECONDS = 3600  # 1 hour
    COMPONENT_NAME = "nudge_worker"

    def __init__(self) -> None:
        super().__init__()
        self.generator = NudgeGeneratorService()
        self.delivery = NudgeDeliveryService()

    async def _process_items(self) -> None:
        """Process all workspaces: generate then deliver nudges."""
        async with AsyncSessionLocal() as db:
            await self._process_workspaces(db)

    async def _process_workspaces(self, db: AsyncSession) -> None:
        """Iterate active workspaces and run nudge generation + delivery."""
        result = await db.execute(
            select(Workspace).where(Workspace.is_active.is_(True))
        )
        workspaces = result.scalars().all()

        for workspace in workspaces:
            nudge_settings = workspace.settings.get("nudge_settings", {})
            if not nudge_settings.get("enabled", True):
                continue

            try:
                # Phase 1: Generate nudges
                generated = await self.generator.generate_for_workspace(
                    db, workspace
                )
                if generated:
                    self.logger.info(
                        "Nudges generated",
                        workspace_id=str(workspace.id),
                        count=generated,
                    )

                # Phase 2: Deliver pending nudges
                delivered = await self.delivery.deliver_pending_nudges(
                    db, workspace.id
                )
                if delivered:
                    self.logger.info(
                        "Nudges delivered",
                        workspace_id=str(workspace.id),
                        count=delivered,
                    )

            except Exception:
                self.logger.exception(
                    "Error processing nudges for workspace",
                    workspace_id=str(workspace.id),
                )


# Singleton registry
_registry = WorkerRegistry(NudgeWorker)
start_nudge_worker = _registry.start
stop_nudge_worker = _registry.stop
get_nudge_worker = _registry.get
