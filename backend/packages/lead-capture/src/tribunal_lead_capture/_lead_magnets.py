"""Lead magnet management endpoints (authenticated, workspace-scoped).

Mounted by :func:`tribunal_lead_capture.get_router` under
``/workspaces/{workspace_id}/lead-magnets``.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.crud import get_or_404
from app.core_api import DB, CurrentUser, get_workspace, paginate
from app.models.workspace import Workspace
from app.services.ai.lead_magnet_generator import (
    generate_calculator_content,
    generate_quiz_content,
)

from .models import LeadMagnet
from .schemas import (
    CalculatorGenerationRequest,
    GeneratedCalculatorContent,
    GeneratedQuizContent,
    LeadMagnetCreate,
    LeadMagnetResponse,
    LeadMagnetUpdate,
    PaginatedLeadMagnets,
    QuizGenerationRequest,
)

router = APIRouter()

RICH_CONTENT_MAGNET_TYPES = {"quiz", "calculator", "rich_text"}


def validate_lead_magnet_content(
    magnet_type: str,
    content_url: str | None,
    content_data: dict[str, Any] | None,
) -> None:
    """Ensure rich magnets carry builder data and URL-backed magnets carry a URL."""
    if magnet_type in RICH_CONTENT_MAGNET_TYPES:
        if not content_data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="content_data is required for quiz, calculator, and rich_text lead magnets",
            )
        return

    if not content_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="content_url is required for URL-backed lead magnets",
        )


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

    query = query.order_by(LeadMagnet.created_at.desc())
    result = await paginate(db, query, page=page, page_size=page_size)

    return PaginatedLeadMagnets(**result.to_response(LeadMagnetResponse))


@router.post("", response_model=LeadMagnetResponse, status_code=status.HTTP_201_CREATED)
async def create_lead_magnet(
    workspace_id: uuid.UUID,
    lead_magnet_in: LeadMagnetCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> LeadMagnet:
    """Create a new lead magnet."""
    lead_magnet_data = lead_magnet_in.model_dump()
    validate_lead_magnet_content(
        magnet_type=str(lead_magnet_data["magnet_type"]),
        content_url=lead_magnet_data.get("content_url"),
        content_data=lead_magnet_data.get("content_data"),
    )

    lead_magnet = LeadMagnet(
        workspace_id=workspace_id,
        **lead_magnet_data,
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
    return await get_or_404(db, LeadMagnet, lead_magnet_id, workspace_id=workspace_id)


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
    lead_magnet = await get_or_404(db, LeadMagnet, lead_magnet_id, workspace_id=workspace_id)

    # Update fields
    update_data = lead_magnet_in.model_dump(exclude_unset=True)
    validate_lead_magnet_content(
        magnet_type=str(update_data.get("magnet_type", lead_magnet.magnet_type)),
        content_url=update_data.get("content_url", lead_magnet.content_url),
        content_data=update_data.get("content_data", lead_magnet.content_data),
    )

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
    lead_magnet = await get_or_404(db, LeadMagnet, lead_magnet_id, workspace_id=workspace_id)
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
    lead_magnet = await get_or_404(db, LeadMagnet, lead_magnet_id, workspace_id=workspace_id)
    lead_magnet.download_count += 1
    await db.commit()
    await db.refresh(lead_magnet)

    return lead_magnet
