"""Phone number management endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.phone_number import PhoneNumber
from app.models.workspace import Workspace

router = APIRouter()


class PhoneNumberResponse(BaseModel):
    """Phone number response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    phone_number: str
    friendly_name: str | None
    sms_enabled: bool
    voice_enabled: bool
    mms_enabled: bool
    assigned_agent_id: uuid.UUID | None
    is_active: bool


class PaginatedPhoneNumbers(BaseModel):
    """Paginated phone numbers response."""

    items: list[PhoneNumberResponse]
    total: int
    page: int
    page_size: int
    pages: int


@router.get("", response_model=PaginatedPhoneNumbers)
async def list_phone_numbers(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    sms_enabled: bool | None = None,
    active_only: bool = True,
) -> PaginatedPhoneNumbers:
    """List phone numbers in a workspace."""
    query = select(PhoneNumber).where(PhoneNumber.workspace_id == workspace_id)

    if active_only:
        query = query.where(PhoneNumber.is_active.is_(True))

    if sms_enabled is not None:
        query = query.where(PhoneNumber.sms_enabled == sms_enabled)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(PhoneNumber.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    phone_numbers = result.scalars().all()

    return PaginatedPhoneNumbers(
        items=[PhoneNumberResponse.model_validate(p) for p in phone_numbers],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/{phone_number_id}", response_model=PhoneNumberResponse)
async def get_phone_number(
    workspace_id: uuid.UUID,
    phone_number_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PhoneNumber:
    """Get a phone number by ID."""
    result = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.id == phone_number_id,
            PhoneNumber.workspace_id == workspace_id,
        )
    )
    phone_number = result.scalar_one_or_none()

    if not phone_number:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not found",
        )

    return phone_number
