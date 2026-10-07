"""DB-backed regressions: moving a deal between stages keeps status in sync.

Marked ``integration`` (run with ``-m integration``); these drive the real
``OpportunityService.update_opportunity`` path against local Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal, engine
from app.models.opportunity import Opportunity, OpportunityActivity
from app.models.pipeline import Pipeline, PipelineStage
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.opportunity import OpportunityCreate, OpportunityUpdate
from app.services.exceptions import NotFoundError, ValidationError
from app.services.opportunities.opportunity_service import OpportunityService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
async def _fresh_engine_pool():
    await engine.dispose()
    yield
    await engine.dispose()


async def _user(db) -> User:
    user = User(
        email=f"stage-outcome-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        full_name="Stage Tester",
    )
    db.add(user)
    await db.flush()
    return user


async def _board(db) -> tuple[Workspace, Pipeline, dict[str, PipelineStage]]:
    ws = Workspace(id=uuid.uuid4(), name="Outcome", slug=f"outcome-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    await db.flush()
    pipeline = Pipeline(workspace_id=ws.id, name="Sales", is_active=True)
    db.add(pipeline)
    await db.flush()
    stages = {
        "lead": PipelineStage(pipeline_id=pipeline.id, name="Lead", order=0, probability=10),
        "proposal": PipelineStage(
            pipeline_id=pipeline.id, name="Proposal", order=1, probability=60
        ),
        "won": PipelineStage(
            pipeline_id=pipeline.id, name="Won", order=2, probability=100, stage_type="won"
        ),
        "lost": PipelineStage(
            pipeline_id=pipeline.id, name="Lost", order=3, probability=0, stage_type="lost"
        ),
    }
    db.add_all(stages.values())
    await db.commit()
    return ws, pipeline, stages


async def _deal(db, ws: Workspace, pipeline: Pipeline, stage: PipelineStage) -> uuid.UUID:
    created = await OpportunityService(db).create_opportunity(
        ws.id,
        OpportunityCreate(pipeline_id=pipeline.id, stage_id=stage.id, name="Deal", amount=5000),
    )
    return created.id


async def _activities(db, opportunity_id: uuid.UUID) -> list[OpportunityActivity]:
    rows = await db.execute(
        select(OpportunityActivity)
        .where(OpportunityActivity.opportunity_id == opportunity_id)
        .order_by(OpportunityActivity.created_at, OpportunityActivity.id)
    )
    return list(rows.scalars())


async def test_move_to_won_stage_closes_deal_as_won() -> None:
    async with AsyncSessionLocal() as db:
        user = await _user(db)
        ws, pipeline, stages = await _board(db)
        deal_id = await _deal(db, ws, pipeline, stages["lead"])

        result = await OpportunityService(db).update_opportunity(
            ws.id, deal_id, OpportunityUpdate(stage_id=stages["won"].id), user_id=user.id
        )

        assert result.stage_id == stages["won"].id
        assert result.status == "won"
        assert result.probability == 100
        assert result.closed_date == datetime.now(UTC).date()
        assert result.closed_by_id == user.id
        types = [(a.activity_type, a.new_value, a.user_id) for a in await _activities(db, deal_id)]
        assert ("stage_changed", "Won", user.id) in types
        assert ("status_changed", "won", user.id) in types


async def test_move_to_lost_stage_closes_deal_as_lost() -> None:
    async with AsyncSessionLocal() as db:
        user = await _user(db)
        ws, pipeline, stages = await _board(db)
        deal_id = await _deal(db, ws, pipeline, stages["proposal"])

        result = await OpportunityService(db).update_opportunity(
            ws.id,
            deal_id,
            OpportunityUpdate(stage_id=stages["lost"].id, lost_reason="Price"),
            user_id=user.id,
        )

        assert result.status == "lost"
        assert result.probability == 0
        assert result.lost_reason == "Price"
        assert result.closed_date == datetime.now(UTC).date()
        assert result.closed_by_id == user.id


async def test_move_back_to_open_stage_reopens_deal() -> None:
    """Undo of a Won drop: the deal goes back to open with close metadata cleared."""
    async with AsyncSessionLocal() as db:
        user = await _user(db)
        ws, pipeline, stages = await _board(db)
        deal_id = await _deal(db, ws, pipeline, stages["proposal"])
        service = OpportunityService(db)
        await service.update_opportunity(
            ws.id, deal_id, OpportunityUpdate(stage_id=stages["won"].id), user_id=user.id
        )

        result = await service.update_opportunity(
            ws.id, deal_id, OpportunityUpdate(stage_id=stages["proposal"].id), user_id=user.id
        )

        assert result.stage_id == stages["proposal"].id
        assert result.status == "open"
        assert result.probability == 60
        assert result.closed_date is None
        assert result.closed_by_id is None
        status_changes = [
            (a.old_value, a.new_value)
            for a in await _activities(db, deal_id)
            if a.activity_type == "status_changed"
        ]
        assert status_changes == [("open", "won"), ("won", "open")]


async def test_won_to_lost_switches_outcome() -> None:
    async with AsyncSessionLocal() as db:
        user = await _user(db)
        ws, pipeline, stages = await _board(db)
        deal_id = await _deal(db, ws, pipeline, stages["lead"])
        service = OpportunityService(db)
        await service.update_opportunity(
            ws.id, deal_id, OpportunityUpdate(stage_id=stages["won"].id), user_id=user.id
        )

        result = await service.update_opportunity(
            ws.id, deal_id, OpportunityUpdate(stage_id=stages["lost"].id), user_id=user.id
        )

        assert result.status == "lost"
        assert result.closed_date is not None


async def test_same_stage_update_is_a_no_op() -> None:
    async with AsyncSessionLocal() as db:
        user = await _user(db)
        ws, pipeline, stages = await _board(db)
        deal_id = await _deal(db, ws, pipeline, stages["lead"])
        service = OpportunityService(db)
        await service.update_opportunity(
            ws.id, deal_id, OpportunityUpdate(stage_id=stages["won"].id), user_id=user.id
        )
        before = len(await _activities(db, deal_id))

        result = await service.update_opportunity(
            ws.id, deal_id, OpportunityUpdate(stage_id=stages["won"].id), user_id=user.id
        )

        assert result.status == "won"
        assert result.closed_date == datetime.now(UTC).date()
        assert len(await _activities(db, deal_id)) == before


async def test_status_only_update_still_supported() -> None:
    """Explicit status changes without a stage move keep working (e.g. abandoned)."""
    async with AsyncSessionLocal() as db:
        user = await _user(db)
        ws, pipeline, stages = await _board(db)
        deal_id = await _deal(db, ws, pipeline, stages["proposal"])

        result = await OpportunityService(db).update_opportunity(
            ws.id, deal_id, OpportunityUpdate(status="abandoned"), user_id=user.id
        )

        assert result.stage_id == stages["proposal"].id
        assert result.status == "abandoned"
        assert result.closed_date is not None
        assert result.closed_by_id == user.id


async def test_conflicting_status_with_outcome_stage_is_rejected() -> None:
    async with AsyncSessionLocal() as db:
        user = await _user(db)
        ws, pipeline, stages = await _board(db)
        deal_id = await _deal(db, ws, pipeline, stages["lead"])

        with pytest.raises(ValidationError):
            await OpportunityService(db).update_opportunity(
                ws.id,
                deal_id,
                OpportunityUpdate(stage_id=stages["won"].id, status="lost"),
                user_id=user.id,
            )


async def test_stage_from_other_pipeline_is_rejected() -> None:
    async with AsyncSessionLocal() as db:
        user = await _user(db)
        ws, pipeline, stages = await _board(db)
        other = Pipeline(workspace_id=ws.id, name="Other", is_active=True)
        db.add(other)
        await db.flush()
        foreign_won = PipelineStage(
            pipeline_id=other.id, name="Won", order=0, probability=100, stage_type="won"
        )
        db.add(foreign_won)
        await db.commit()
        deal_id = await _deal(db, ws, pipeline, stages["lead"])
        lead_stage_id = stages["lead"].id

        with pytest.raises(NotFoundError):
            await OpportunityService(db).update_opportunity(
                ws.id, deal_id, OpportunityUpdate(stage_id=foreign_won.id), user_id=user.id
            )
        await db.rollback()

        deal = await db.get(Opportunity, deal_id)
        assert deal is not None
        assert deal.stage_id == lead_stage_id
        assert deal.status == "open"


async def test_stage_from_other_workspace_is_rejected() -> None:
    async with AsyncSessionLocal() as db:
        user = await _user(db)
        ws, pipeline, stages = await _board(db)
        _other_ws, _other_pipeline, other_stages = await _board(db)
        deal_id = await _deal(db, ws, pipeline, stages["lead"])

        with pytest.raises(NotFoundError):
            await OpportunityService(db).update_opportunity(
                ws.id, deal_id, OpportunityUpdate(stage_id=other_stages["won"].id), user_id=user.id
            )
        await db.rollback()

        deal = await db.get(Opportunity, deal_id)
        assert deal is not None
        assert deal.status == "open"
        assert deal.closed_date is None
