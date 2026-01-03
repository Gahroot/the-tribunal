"""Offer management endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.lead_magnet import LeadMagnet
from app.models.offer import Offer
from app.models.offer_lead_magnet import OfferLeadMagnet
from app.models.workspace import Workspace
from app.schemas.lead_magnet import LeadMagnetResponse
from app.schemas.offer import (
    OfferCreate,
    OfferResponse,
    OfferResponseWithLeadMagnets,
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


@router.get("/{offer_id}/with-lead-magnets", response_model=OfferResponseWithLeadMagnets)
async def get_offer_with_lead_magnets(
    workspace_id: uuid.UUID,
    offer_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> OfferResponseWithLeadMagnets:
    """Get an offer with its attached lead magnets."""
    result = await db.execute(
        select(Offer)
        .options(
            selectinload(Offer.offer_lead_magnets).selectinload(OfferLeadMagnet.lead_magnet)
        )
        .where(
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

    # Extract lead magnets and calculate total value
    lead_magnets = [
        LeadMagnetResponse.model_validate(olm.lead_magnet)
        for olm in sorted(offer.offer_lead_magnets, key=lambda x: x.sort_order)
    ]

    # Calculate total value from value stack and lead magnets
    total_value = 0.0
    if offer.value_stack_items:
        for item in offer.value_stack_items:
            if item.get("included", True):
                value = item.get("value", 0)
                if isinstance(value, (int, float)):
                    total_value += value
    for lm in lead_magnets:
        if lm.estimated_value:
            total_value += lm.estimated_value

    return OfferResponseWithLeadMagnets(
        **OfferResponse.model_validate(offer).model_dump(),
        lead_magnets=lead_magnets,
        total_value=total_value if total_value > 0 else None,
    )


@router.post("/{offer_id}/lead-magnets", response_model=OfferResponseWithLeadMagnets)
async def attach_lead_magnets(
    workspace_id: uuid.UUID,
    offer_id: uuid.UUID,
    lead_magnet_ids: list[uuid.UUID],
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> OfferResponseWithLeadMagnets:
    """Attach lead magnets to an offer."""
    # Verify offer exists
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

    # Verify all lead magnets exist in this workspace
    result = await db.execute(
        select(LeadMagnet).where(
            LeadMagnet.id.in_(lead_magnet_ids),
            LeadMagnet.workspace_id == workspace_id,
        )
    )
    found_magnets = {lm.id for lm in result.scalars().all()}

    missing = set(lead_magnet_ids) - found_magnets
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead magnets not found: {missing}",
        )

    # Get current max sort order
    max_order_result = await db.execute(
        select(func.max(OfferLeadMagnet.sort_order)).where(
            OfferLeadMagnet.offer_id == offer_id
        )
    )
    max_order: int = max_order_result.scalar() or 0

    # Attach lead magnets (skip if already attached)
    result = await db.execute(
        select(OfferLeadMagnet.lead_magnet_id).where(
            OfferLeadMagnet.offer_id == offer_id
        )
    )
    existing_ids = {row[0] for row in result.all()}

    for idx, lm_id in enumerate(lead_magnet_ids):
        if lm_id not in existing_ids:
            association = OfferLeadMagnet(
                offer_id=offer_id,
                lead_magnet_id=lm_id,
                sort_order=max_order + idx + 1,
                is_bonus=True,
            )
            db.add(association)

    await db.commit()

    # Return updated offer with lead magnets
    return await get_offer_with_lead_magnets(
        workspace_id=workspace_id,
        offer_id=offer_id,
        current_user=current_user,
        db=db,
        workspace=workspace,
    )


@router.delete("/{offer_id}/lead-magnets/{lead_magnet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_lead_magnet(
    workspace_id: uuid.UUID,
    offer_id: uuid.UUID,
    lead_magnet_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Detach a lead magnet from an offer."""
    # Verify offer exists in workspace
    result = await db.execute(
        select(Offer).where(
            Offer.id == offer_id,
            Offer.workspace_id == workspace_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )

    # Find and delete the association
    result = await db.execute(
        select(OfferLeadMagnet).where(
            OfferLeadMagnet.offer_id == offer_id,
            OfferLeadMagnet.lead_magnet_id == lead_magnet_id,
        )
    )
    association = result.scalar_one_or_none()

    if not association:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead magnet not attached to this offer",
        )

    await db.delete(association)
    await db.commit()


@router.put("/{offer_id}/lead-magnets/reorder", response_model=OfferResponseWithLeadMagnets)
async def reorder_lead_magnets(
    workspace_id: uuid.UUID,
    offer_id: uuid.UUID,
    lead_magnet_ids: list[uuid.UUID],
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> OfferResponseWithLeadMagnets:
    """Reorder lead magnets attached to an offer."""
    # Verify offer exists
    result = await db.execute(
        select(Offer).where(
            Offer.id == offer_id,
            Offer.workspace_id == workspace_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )

    # Update sort order for each lead magnet
    for idx, lm_id in enumerate(lead_magnet_ids):
        assoc_result = await db.execute(
            select(OfferLeadMagnet).where(
                OfferLeadMagnet.offer_id == offer_id,
                OfferLeadMagnet.lead_magnet_id == lm_id,
            )
        )
        association: OfferLeadMagnet | None = assoc_result.scalar_one_or_none()
        if association:
            association.sort_order = idx

    await db.commit()

    return await get_offer_with_lead_magnets(
        workspace_id=workspace_id,
        offer_id=offer_id,
        current_user=current_user,
        db=db,
        workspace=workspace,
    )
