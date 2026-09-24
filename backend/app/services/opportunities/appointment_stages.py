"""Move open deals through appointment stages without changing won/lost deals.

Stages are scoped to each deal's existing pipeline; custom pipelines retain their
own columns. The pipeline row lock serializes creation on concurrent webhooks.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity
from app.models.pipeline import Pipeline, PipelineStage

STAGES = {"scheduled": ("Booked", 40), "completed": ("Showed", 60), "no_show": ("No Show", 10)}


async def move_appointment_opportunities(
    db: AsyncSession, workspace_id: uuid.UUID, contact_id: int, status: str
) -> None:
    """Advance open opportunities for the primary contact; caller commits."""
    if status not in STAGES:
        return
    deals = (
        await db.scalars(
            select(Opportunity).where(
                Opportunity.workspace_id == workspace_id,
                Opportunity.primary_contact_id == contact_id,
                Opportunity.status == "open",
                Opportunity.is_active.is_(True),
            )
        )
    ).all()
    name, probability = STAGES[status]
    for pipeline_id in sorted({deal.pipeline_id for deal in deals}):
        pipeline = await db.scalar(
            select(Pipeline)
            .where(Pipeline.id == pipeline_id, Pipeline.workspace_id == workspace_id)
            .with_for_update()
        )
        if pipeline is None:
            continue
        stage = await db.scalar(
            select(PipelineStage)
            .where(
                PipelineStage.pipeline_id == pipeline_id,
                func.lower(PipelineStage.name) == name.lower(),
            )
            .order_by(PipelineStage.order)
            .limit(1)
        )
        if stage is None:
            next_order = await db.scalar(
                select(func.coalesce(func.max(PipelineStage.order), 0) + 1).where(
                    PipelineStage.pipeline_id == pipeline_id
                )
            )
            stage = PipelineStage(
                pipeline_id=pipeline_id,
                name=name,
                order=next_order,
                probability=probability,
                stage_type="active",
            )
            db.add(stage)
            await db.flush()
        for deal in deals:
            if deal.pipeline_id == pipeline_id and deal.stage_id != stage.id:
                deal.stage_id = stage.id
                deal.probability = stage.probability
                deal.stage_changed_at = datetime.now(UTC)
