"""Opportunity management endpoints."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.workspace import Workspace
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
from app.services.opportunities import OpportunityService

router = APIRouter()


# Pipeline endpoints
@router.get("/pipelines", response_model=list[PipelineResponse])
async def list_pipelines(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> list[PipelineResponse]:
    """List all pipelines in a workspace."""
    service = OpportunityService(db)
    return await service.list_pipelines(workspace_id)


@router.post("/pipelines", response_model=PipelineResponse, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    workspace_id: uuid.UUID,
    pipeline_in: PipelineCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PipelineResponse:
    """Create a new pipeline."""
    service = OpportunityService(db)
    return await service.create_pipeline(workspace_id, pipeline_in)


@router.get("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def get_pipeline(
    workspace_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PipelineResponse:
    """Get a specific pipeline."""
    service = OpportunityService(db)
    return await service.get_pipeline(workspace_id, pipeline_id)


@router.put("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def update_pipeline(
    workspace_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    pipeline_in: PipelineUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PipelineResponse:
    """Update a pipeline."""
    service = OpportunityService(db)
    return await service.update_pipeline(workspace_id, pipeline_id, pipeline_in)


@router.delete("/pipelines/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(
    workspace_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete a pipeline."""
    service = OpportunityService(db)
    await service.delete_pipeline(workspace_id, pipeline_id)


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
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PipelineStageResponse:
    """Create a new pipeline stage."""
    service = OpportunityService(db)
    return await service.create_pipeline_stage(workspace_id, pipeline_id, stage_in)


@router.put("/pipelines/{pipeline_id}/stages/{stage_id}", response_model=PipelineStageResponse)
async def update_pipeline_stage(
    workspace_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    stage_id: uuid.UUID,
    stage_in: PipelineStageUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PipelineStageResponse:
    """Update a pipeline stage."""
    service = OpportunityService(db)
    return await service.update_pipeline_stage(pipeline_id, stage_id, stage_in)


# Opportunity endpoints
@router.get("", response_model=PaginatedOpportunities)
async def list_opportunities(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    pipeline_id: Annotated[uuid.UUID | None, Query()] = None,
    stage_id: Annotated[uuid.UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    search: str | None = None,
) -> PaginatedOpportunities:
    """List opportunities in a workspace."""
    service = OpportunityService(db)
    return await service.list_opportunities(
        workspace_id,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        page=page,
        page_size=page_size,
        search=search,
    )


@router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    workspace_id: uuid.UUID,
    opportunity_in: OpportunityCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> OpportunityResponse:
    """Create a new opportunity."""
    service = OpportunityService(db)
    return await service.create_opportunity(workspace_id, opportunity_in)


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse)
async def get_opportunity(
    workspace_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> OpportunityDetailResponse:
    """Get a specific opportunity."""
    service = OpportunityService(db)
    return await service.get_opportunity(workspace_id, opportunity_id)


@router.put("/{opportunity_id}", response_model=OpportunityResponse)
async def update_opportunity(
    workspace_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    opportunity_in: OpportunityUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> OpportunityResponse:
    """Update an opportunity."""
    service = OpportunityService(db)
    return await service.update_opportunity(
        workspace_id, opportunity_id, opportunity_in, current_user.id
    )


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_opportunity(
    workspace_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete an opportunity."""
    service = OpportunityService(db)
    await service.delete_opportunity(workspace_id, opportunity_id)


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
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, Any]:
    """Create a line item for an opportunity."""
    service = OpportunityService(db)
    return await service.create_line_item(workspace_id, opportunity_id, item_in)


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
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, Any]:
    """Update a line item."""
    service = OpportunityService(db)
    return await service.update_line_item(workspace_id, opportunity_id, item_id, item_in)


@router.delete("/{opportunity_id}/line-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_line_item(
    workspace_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete a line item."""
    service = OpportunityService(db)
    await service.delete_line_item(workspace_id, opportunity_id, item_id)
