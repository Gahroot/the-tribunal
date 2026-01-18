"""Lead magnet management endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.lead_magnet import LeadMagnet
from app.models.workspace import Workspace
from app.schemas.lead_magnet import (
    CalculatorGenerationRequest,
    GeneratedCalculatorContent,
    GeneratedQuizContent,
    LeadMagnetCreate,
    LeadMagnetResponse,
    LeadMagnetUpdate,
    PaginatedLeadMagnets,
    QuizGenerationRequest,
)
from app.services.ai.lead_magnet_generator import (
    generate_calculator_content,
    generate_quiz_content,
)

router = APIRouter()


@router.post("/generate-quiz", response_model=GeneratedQuizContent)
async def generate_quiz_ai(
    workspace_id: uuid.UUID,
    request: QuizGenerationRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> GeneratedQuizContent:
    """Generate quiz content using AI."""
    result = await generate_quiz_content(
        topic=request.topic,
        target_audience=request.target_audience,
        goal=request.goal,
        num_questions=request.num_questions,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Failed to generate quiz content"),
        )

    return GeneratedQuizContent(**result)


@router.post("/generate-calculator", response_model=GeneratedCalculatorContent)
async def generate_calculator_ai(
    workspace_id: uuid.UUID,
    request: CalculatorGenerationRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> GeneratedCalculatorContent:
    """Generate calculator content using AI."""
    result = await generate_calculator_content(
        calculator_type=request.calculator_type,
        industry=request.industry,
        target_audience=request.target_audience,
        value_proposition=request.value_proposition,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Failed to generate calculator content"),
        )

    return GeneratedCalculatorContent(**result)


@router.get("", response_model=PaginatedLeadMagnets)
async def list_lead_magnets(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    active_only: bool = False,
    magnet_type: str | None = None,
) -> PaginatedLeadMagnets:
    """List lead magnets in a workspace."""
    query = select(LeadMagnet).where(LeadMagnet.workspace_id == workspace_id)

    if active_only:
        query = query.where(LeadMagnet.is_active.is_(True))

    if magnet_type:
        query = query.where(LeadMagnet.magnet_type == magnet_type)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(LeadMagnet.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    lead_magnets = result.scalars().all()

    return PaginatedLeadMagnets(
        items=[LeadMagnetResponse.model_validate(lm) for lm in lead_magnets],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )


@router.post("", response_model=LeadMagnetResponse, status_code=status.HTTP_201_CREATED)
async def create_lead_magnet(
    workspace_id: uuid.UUID,
    lead_magnet_in: LeadMagnetCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> LeadMagnet:
    """Create a new lead magnet."""
    lead_magnet = LeadMagnet(
        workspace_id=workspace_id,
        **lead_magnet_in.model_dump(),
    )
    db.add(lead_magnet)
    await db.commit()
    await db.refresh(lead_magnet)

    return lead_magnet


@router.get("/{lead_magnet_id}", response_model=LeadMagnetResponse)
async def get_lead_magnet(
    workspace_id: uuid.UUID,
    lead_magnet_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> LeadMagnet:
    """Get a lead magnet by ID."""
    result = await db.execute(
        select(LeadMagnet).where(
            LeadMagnet.id == lead_magnet_id,
            LeadMagnet.workspace_id == workspace_id,
        )
    )
    lead_magnet = result.scalar_one_or_none()

    if not lead_magnet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead magnet not found",
        )

    return lead_magnet


@router.put("/{lead_magnet_id}", response_model=LeadMagnetResponse)
async def update_lead_magnet(
    workspace_id: uuid.UUID,
    lead_magnet_id: uuid.UUID,
    lead_magnet_in: LeadMagnetUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> LeadMagnet:
    """Update a lead magnet."""
    result = await db.execute(
        select(LeadMagnet).where(
            LeadMagnet.id == lead_magnet_id,
            LeadMagnet.workspace_id == workspace_id,
        )
    )
    lead_magnet = result.scalar_one_or_none()

    if not lead_magnet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead magnet not found",
        )

    # Update fields
    update_data = lead_magnet_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(lead_magnet, field, value)

    await db.commit()
    await db.refresh(lead_magnet)

    return lead_magnet


@router.delete("/{lead_magnet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead_magnet(
    workspace_id: uuid.UUID,
    lead_magnet_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete a lead magnet."""
    result = await db.execute(
        select(LeadMagnet).where(
            LeadMagnet.id == lead_magnet_id,
            LeadMagnet.workspace_id == workspace_id,
        )
    )
    lead_magnet = result.scalar_one_or_none()

    if not lead_magnet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead magnet not found",
        )

    await db.delete(lead_magnet)
    await db.commit()


@router.post("/{lead_magnet_id}/increment-download", response_model=LeadMagnetResponse)
async def increment_download_count(
    workspace_id: uuid.UUID,
    lead_magnet_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> LeadMagnet:
    """Increment the download count for a lead magnet."""
    result = await db.execute(
        select(LeadMagnet).where(
            LeadMagnet.id == lead_magnet_id,
            LeadMagnet.workspace_id == workspace_id,
        )
    )
    lead_magnet = result.scalar_one_or_none()

    if not lead_magnet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead magnet not found",
        )

    lead_magnet.download_count += 1
    await db.commit()
    await db.refresh(lead_magnet)

    return lead_magnet
