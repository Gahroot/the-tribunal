"""Operator report worker — pushes the Today system to the operator's phone.

Flips the daily loop from pull (open the app) to push (it texts you). For each
active workspace whose autonomy mandate enables ``operator_report``, it delivers:

* a morning "here's today's plan" (the ordered mission queue),
* an end-of-day "here's what I did, sold, and am blocked on" recap, and
* immediate human-handoff escalations when a buyer wants add-ons beyond the
  batch (running ads, AI-agent install, consulting).

Delivery, quiet hours, and once-per-day idempotency live in
:class:`OperatorReportService`; this worker just iterates workspaces on a poll
cadence and lets the service decide what (if anything) is due right now.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.workspace import Workspace
from app.services.reporting.operator_report_service import OperatorReportService
from app.workers.base import BaseWorker, WorkerRegistry
from app.workers.retryable import RetryableWorker


class OperatorReportWorker(RetryableWorker, BaseWorker):
    """Background worker delivering proactive operator reports over iMessage."""

    POLL_INTERVAL_SECONDS = settings.operator_report_poll_interval
    COMPONENT_NAME = "operator_report_worker"
    # One reporting pass per workspace; sends fan out to a single operator each,
    # so modest concurrency is plenty and keeps relay sends from bursting.
    MAX_CONCURRENCY = 3

    def __init__(self) -> None:
        super().__init__()
        self.service = OperatorReportService()

    async def _process_items(self) -> None:
        async with AsyncSessionLocal() as db:
            await self._process_workspaces(db)

    async def _process_workspaces(self, db: AsyncSession) -> None:
        result = await db.execute(select(Workspace).where(Workspace.is_active.is_(True)))
        workspaces = result.scalars().all()
        for workspace in workspaces:
            await self.execute_with_retry(self._process_single_workspace, db, workspace)

    async def _process_single_workspace(self, db: AsyncSession, workspace: Workspace) -> None:
        outcome = await self.service.run_for_workspace(db, workspace)
        if outcome.delivered:
            self.record_items_processed(len(outcome.delivered))
            self.logger.info(
                "operator_reports_delivered",
                workspace_id=str(workspace.id),
                delivered=list(outcome.delivered),
            )


# Singleton registry
_registry = WorkerRegistry(OperatorReportWorker)
start_operator_report_worker = _registry.start
stop_operator_report_worker = _registry.stop
get_operator_report_worker = _registry.get
