"""Opportunity management endpoints."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, get_workspace
from app.db.pagination import paginate
from app.models.opportunity import Opportunity, OpportunityActivity, OpportunityLineItem
from app.models.pipeline import Pipeline, PipelineStage
from app.schemas.opportunity import (
    OpportunityCreate,
    OpportunityDetailResponse,
    OpportunityLineItemCreate,
    OpportunityLineItemUpdate,
    OpportunityResponse,
    OpportunityUpdate,
    PaginatedOpportunities,
    PipelineCreate,
    PipelineResponse,
    PipelineStageCreate,
    PipelineStageResponse,
    PipelineStageUpdate,
    PipelineUpdate,
)

router = APIRouter()


# Pipeline endpoints
@router.get("/pipelines", response_model=list[PipelineResponse])
async def list_pipelines(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> list[PipelineResponse]:
    """List all pipelines in a workspace."""
    await get_workspace(workspace_id, current_user, db)

    query = (
        select(Pipeline)
        .where(Pipeline.workspace_id == workspace_id)
        .where(Pipeline.is_active)
        .options(selectinload(Pipeline.stages))
    )
    result = await db.execute(query)
    pipelines = result.unique().scalars().all()

    return [PipelineResponse.model_validate(p) for p in pipelines]


@router.post("/pipelines", response_model=PipelineResponse, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    workspace_id: uuid.UUID,
    pipeline_in: PipelineCreate,
    current_user: CurrentUser,
    db: DB,
) -> PipelineResponse:
    """Create a new pipeline."""
    await get_workspace(workspace_id, current_user, db)

    pipeline = Pipeline(
        workspace_id=workspace_id,
        name=pipeline_in.name,
        description=pipeline_in.description,
    )
    db.add(pipeline)
    await db.flush()

    # Create default stages
    default_stages = [
        PipelineStage(
            pipeline_id=pipeline.id,
            name="New",
            order=0,
            probability=0,
            stage_type="active",
        ),
        PipelineStage(
            pipeline_id=pipeline.id,
            name="Qualified",
            order=1,
            probability=25,
            stage_type="active",
        ),
        PipelineStage(
            pipeline_id=pipeline.id,
            name="Proposal",
            order=2,
            probability=50,
            stage_type="active",
        ),
        PipelineStage(
            pipeline_id=pipeline.id,
            name="Won",
            order=3,
            probability=100,
            stage_type="won",
        ),
        PipelineStage(
            pipeline_id=pipeline.id,
            name="Lost",
            order=4,
            probability=0,
            stage_type="lost",
        ),
    ]
    for stage in default_stages:
        db.add(stage)

    await db.commit()
    await db.refresh(pipeline, ["stages"])

    return PipelineResponse.model_validate(pipeline)


@router.get("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def get_pipeline(
    workspace_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> PipelineResponse:
    """Get a specific pipeline."""
    await get_workspace(workspace_id, current_user, db)

    query = (
        select(Pipeline)
        .where((Pipeline.id == pipeline_id) & (Pipeline.workspace_id == workspace_id))
        .options(selectinload(Pipeline.stages))
    )
    result = await db.execute(query)
    pipeline = result.unique().scalar_one_or_none()

    if not pipeline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    return PipelineResponse.model_validate(pipeline)


@router.put("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def update_pipeline(
    workspace_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    pipeline_in: PipelineUpdate,
    current_user: CurrentUser,
    db: DB,
) -> PipelineResponse:
    """Update a pipeline."""
    await get_workspace(workspace_id, current_user, db)

    query = select(Pipeline).where(
        (Pipeline.id == pipeline_id) & (Pipeline.workspace_id == workspace_id)
    )
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    if pipeline_in.name is not None:
        pipeline.name = pipeline_in.name
    if pipeline_in.description is not None:
        pipeline.description = pipeline_in.description
    if pipeline_in.is_active is not None:
        pipeline.is_active = pipeline_in.is_active

    await db.commit()
    await db.refresh(pipeline)

    return PipelineResponse.model_validate(pipeline)


@router.delete("/pipelines/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(
    workspace_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Delete a pipeline."""
    await get_workspace(workspace_id, current_user, db)

    query = select(Pipeline).where(
        (Pipeline.id == pipeline_id) & (Pipeline.workspace_id == workspace_id)
    )
    result = await db.execute(query)
    pipeline = result.scalar_one_or_none()

    if not pipeline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    await db.delete(pipeline)
    await db.commit()


# Pipeline stage endpoints
@router.post(
    "/pipelines/{pipeline_id}/stages",
    response_model=PipelineStageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_pipeline_stage(
    workspace_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    stage_in: PipelineStageCreate,
    current_user: CurrentUser,
    db: DB,
) -> PipelineStageResponse:
    """Create a new pipeline stage."""
    await get_workspace(workspace_id, current_user, db)

    # Verify pipeline exists
    pipeline_query = select(Pipeline).where(
        (Pipeline.id == pipeline_id) & (Pipeline.workspace_id == workspace_id)
    )
    pipeline_result = await db.execute(pipeline_query)
    if not pipeline_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    stage = PipelineStage(
        pipeline_id=pipeline_id,
        name=stage_in.name,
        description=stage_in.description,
        order=stage_in.order,
        probability=stage_in.probability,
        stage_type=stage_in.stage_type,
    )
    db.add(stage)
    await db.commit()
    await db.refresh(stage)

    return PipelineStageResponse.model_validate(stage)


@router.put("/pipelines/{pipeline_id}/stages/{stage_id}", response_model=PipelineStageResponse)
async def update_pipeline_stage(
    workspace_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    stage_id: uuid.UUID,
    stage_in: PipelineStageUpdate,
    current_user: CurrentUser,
    db: DB,
) -> PipelineStageResponse:
    """Update a pipeline stage."""
    await get_workspace(workspace_id, current_user, db)

    query = select(PipelineStage).where(
        (PipelineStage.id == stage_id) & (PipelineStage.pipeline_id == pipeline_id)
    )
    result = await db.execute(query)
    stage = result.scalar_one_or_none()

    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

    if stage_in.name is not None:
        stage.name = stage_in.name
    if stage_in.description is not None:
        stage.description = stage_in.description
    if stage_in.order is not None:
        stage.order = stage_in.order
    if stage_in.probability is not None:
        stage.probability = stage_in.probability
    if stage_in.stage_type is not None:
        stage.stage_type = stage_in.stage_type

    await db.commit()
    await db.refresh(stage)

    return PipelineStageResponse.model_validate(stage)


# Opportunity endpoints
@router.get("", response_model=PaginatedOpportunities)
async def list_opportunities(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    pipeline_id: Annotated[uuid.UUID | None, Query()] = None,
    stage_id: Annotated[uuid.UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    search: str | None = None,
) -> PaginatedOpportunities:
    """List opportunities in a workspace."""
    await get_workspace(workspace_id, current_user, db)

    query = select(Opportunity).where(Opportunity.workspace_id == workspace_id)

    if pipeline_id:
        query = query.where(Opportunity.pipeline_id == pipeline_id)

    if stage_id:
        query = query.where(Opportunity.stage_id == stage_id)

    if search:
        search_term = f"%{search}%"
        query = query.where(Opportunity.name.ilike(search_term))

    query = query.order_by(Opportunity.created_at.desc())
    result = await paginate(db, query, page=page, page_size=page_size)

    return PaginatedOpportunities(
        items=[OpportunityResponse.model_validate(o) for o in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        pages=result.pages,
    )


@router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    workspace_id: uuid.UUID,
    opportunity_in: OpportunityCreate,
    current_user: CurrentUser,
    db: DB,
) -> OpportunityResponse:
    """Create a new opportunity."""
    await get_workspace(workspace_id, current_user, db)

    # Verify pipeline exists
    pipeline_query = select(Pipeline).where(
        (Pipeline.id == opportunity_in.pipeline_id) & (Pipeline.workspace_id == workspace_id)
    )
    pipeline = (await db.execute(pipeline_query)).scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    # Verify stage if provided
    stage = None
    if opportunity_in.stage_id:
        stage_query = select(PipelineStage).where(PipelineStage.id == opportunity_in.stage_id)
        stage = (await db.execute(stage_query)).scalar_one_or_none()
        if not stage:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

    opportunity = Opportunity(
        workspace_id=workspace_id,
        pipeline_id=opportunity_in.pipeline_id,
        stage_id=opportunity_in.stage_id,
        primary_contact_id=opportunity_in.primary_contact_id,
        name=opportunity_in.name,
        description=opportunity_in.description,
        amount=opportunity_in.amount,
        currency=opportunity_in.currency,
        expected_close_date=opportunity_in.expected_close_date,
        source=opportunity_in.source,
        probability=stage.probability if stage else 0,
    )
    db.add(opportunity)
    await db.commit()
    await db.refresh(opportunity)

    return OpportunityResponse.model_validate(opportunity)


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse)
async def get_opportunity(
    workspace_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> OpportunityDetailResponse:
    """Get a specific opportunity."""
    await get_workspace(workspace_id, current_user, db)

    query = select(Opportunity).where(
        (Opportunity.id == opportunity_id) & (Opportunity.workspace_id == workspace_id)
    )
    result = await db.execute(query)
    opportunity = result.scalar_one_or_none()

    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    return OpportunityDetailResponse.model_validate(opportunity)


@router.put("/{opportunity_id}", response_model=OpportunityResponse)
async def update_opportunity(
    workspace_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    opportunity_in: OpportunityUpdate,
    current_user: CurrentUser,
    db: DB,
) -> OpportunityResponse:
    """Update an opportunity."""
    await get_workspace(workspace_id, current_user, db)

    query = select(Opportunity).where(
        (Opportunity.id == opportunity_id) & (Opportunity.workspace_id == workspace_id)
    )
    result = await db.execute(query)
    opportunity = result.scalar_one_or_none()

    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    # If stage is being updated, update probability and log activity
    if opportunity_in.stage_id and opportunity_in.stage_id != opportunity.stage_id:
        stage_query = select(PipelineStage).where(PipelineStage.id == opportunity_in.stage_id)
        stage = (await db.execute(stage_query)).scalar_one_or_none()
        if not stage:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

        # Log activity
        old_stage_query = select(PipelineStage).where(PipelineStage.id == opportunity.stage_id)
        old_stage = (await db.execute(old_stage_query)).scalar_one_or_none()

        activity = OpportunityActivity(
            opportunity_id=opportunity_id,
            user_id=current_user.id,
            activity_type="stage_changed",
            old_value=old_stage.name if old_stage else "None",
            new_value=stage.name,
            description=f"Moved from {old_stage.name if old_stage else 'None'} to {stage.name}",
        )
        db.add(activity)

        opportunity.stage_id = opportunity_in.stage_id
        opportunity.probability = stage.probability
        opportunity.stage_changed_at = datetime.now(UTC)

    # Apply simple field updates
    simple_fields = [
        "name", "description", "amount", "currency",
        "expected_close_date", "assigned_user_id", "source", "lost_reason", "is_active"
    ]
    for field in simple_fields:
        value = getattr(opportunity_in, field, None)
        if value is not None:
            setattr(opportunity, field, value)

    # Handle status change with activity logging
    if opportunity_in.status is not None and opportunity_in.status != opportunity.status:
        activity = OpportunityActivity(
            opportunity_id=opportunity_id,
            user_id=current_user.id,
            activity_type="status_changed",
            old_value=opportunity.status,
            new_value=opportunity_in.status,
            description=f"Status changed from {opportunity.status} to {opportunity_in.status}",
        )
        db.add(activity)
        opportunity.status = opportunity_in.status
        # Set closed_date when moving to terminal status
        is_closed = opportunity_in.status in ("won", "lost", "abandoned")
        opportunity.closed_date = datetime.now(UTC).date() if is_closed else None
        opportunity.closed_by_id = current_user.id if is_closed else None

    await db.commit()
    await db.refresh(opportunity)

    return OpportunityResponse.model_validate(opportunity)


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_opportunity(
    workspace_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Delete an opportunity."""
    await get_workspace(workspace_id, current_user, db)

    query = select(Opportunity).where(
        (Opportunity.id == opportunity_id) & (Opportunity.workspace_id == workspace_id)
    )
    result = await db.execute(query)
    opportunity = result.scalar_one_or_none()

    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    await db.delete(opportunity)
    await db.commit()


# Line items endpoints
@router.post(
    "/{opportunity_id}/line-items",
    response_model=dict[str, uuid.UUID | float],
    status_code=status.HTTP_201_CREATED,
)
async def create_line_item(
    workspace_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    item_in: OpportunityLineItemCreate,
    current_user: CurrentUser,
    db: DB,
) -> dict[str, uuid.UUID | float]:
    """Create a line item for an opportunity."""
    await get_workspace(workspace_id, current_user, db)

    # Verify opportunity exists
    opp_query = select(Opportunity).where(
        (Opportunity.id == opportunity_id) & (Opportunity.workspace_id == workspace_id)
    )
    opportunity = (await db.execute(opp_query)).scalar_one_or_none()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    total = (item_in.quantity * item_in.unit_price) - item_in.discount

    line_item = OpportunityLineItem(
        opportunity_id=opportunity_id,
        name=item_in.name,
        description=item_in.description,
        quantity=item_in.quantity,
        unit_price=item_in.unit_price,
        discount=item_in.discount,
        total=total,
    )
    db.add(line_item)
    await db.commit()
    await db.refresh(line_item)

    return {"id": line_item.id, "total": float(line_item.total)}


@router.put(
    "/{opportunity_id}/line-items/{item_id}",
    response_model=dict[str, uuid.UUID | float],
)
async def update_line_item(
    workspace_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    item_id: uuid.UUID,
    item_in: OpportunityLineItemUpdate,
    current_user: CurrentUser,
    db: DB,
) -> dict[str, uuid.UUID | float]:
    """Update a line item."""
    await get_workspace(workspace_id, current_user, db)

    query = select(OpportunityLineItem).where(
        (OpportunityLineItem.id == item_id) & (OpportunityLineItem.opportunity_id == opportunity_id)
    )
    result = await db.execute(query)
    line_item = result.scalar_one_or_none()

    if not line_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")

    if item_in.name is not None:
        line_item.name = item_in.name
    if item_in.description is not None:
        line_item.description = item_in.description
    if item_in.quantity is not None:
        line_item.quantity = item_in.quantity
    if item_in.unit_price is not None:
        line_item.unit_price = item_in.unit_price
    if item_in.discount is not None:
        line_item.discount = item_in.discount

    # Recalculate total
    line_item.total = (line_item.quantity * line_item.unit_price) - line_item.discount

    await db.commit()
    await db.refresh(line_item)

    return {"id": line_item.id, "total": float(line_item.total)}


@router.delete("/{opportunity_id}/line-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_line_item(
    workspace_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Delete a line item."""
    await get_workspace(workspace_id, current_user, db)

    query = select(OpportunityLineItem).where(
        (OpportunityLineItem.id == item_id) & (OpportunityLineItem.opportunity_id == opportunity_id)
    )
    result = await db.execute(query)
    line_item = result.scalar_one_or_none()

    if not line_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")

    await db.delete(line_item)
    await db.commit()
