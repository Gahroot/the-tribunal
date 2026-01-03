"""Offer management endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.offer import Offer
from app.models.workspace import Workspace
from app.schemas.offer import (
    OfferCreate,
    OfferResponse,
    OfferUpdate,
    PaginatedOffers,
)

router = APIRouter()


@router.get("", response_model=PaginatedOffers)
async def list_offers(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    active_only: bool = False,
) -> PaginatedOffers:
    """List offers in a workspace."""
    query = select(Offer).where(Offer.workspace_id == workspace_id)

    if active_only:
        query = query.where(Offer.is_active.is_(True))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(Offer.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    offers = result.scalars().all()

    return PaginatedOffers(
        items=[OfferResponse.model_validate(o) for o in offers],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.post("", response_model=OfferResponse, status_code=status.HTTP_201_CREATED)
async def create_offer(
    workspace_id: uuid.UUID,
    offer_in: OfferCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Offer:
    """Create a new offer."""
    offer = Offer(
        workspace_id=workspace_id,
        **offer_in.model_dump(),
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)

    return offer


@router.get("/{offer_id}", response_model=OfferResponse)
async def get_offer(
    workspace_id: uuid.UUID,
    offer_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Offer:
    """Get an offer by ID."""
    result = await db.execute(
        select(Offer).where(
            Offer.id == offer_id,
            Offer.workspace_id == workspace_id,
        )
    )
    offer = result.scalar_one_or_none()

    if not offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )

    return offer


@router.put("/{offer_id}", response_model=OfferResponse)
async def update_offer(
    workspace_id: uuid.UUID,
    offer_id: uuid.UUID,
    offer_in: OfferUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Offer:
    """Update an offer."""
    result = await db.execute(
        select(Offer).where(
            Offer.id == offer_id,
            Offer.workspace_id == workspace_id,
        )
    )
    offer = result.scalar_one_or_none()

    if not offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )

    # Update fields
    update_data = offer_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(offer, field, value)

    await db.commit()
    await db.refresh(offer)

    return offer


@router.delete("/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_offer(
    workspace_id: uuid.UUID,
    offer_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete an offer."""
    result = await db.execute(
        select(Offer).where(
            Offer.id == offer_id,
            Offer.workspace_id == workspace_id,
        )
    )
    offer = result.scalar_one_or_none()

    if not offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )

    await db.delete(offer)
    await db.commit()
