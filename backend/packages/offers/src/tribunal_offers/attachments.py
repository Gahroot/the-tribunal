"""Exact-set association reconciliation; the caller owns the transaction."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tribunal_lead_capture.models import LeadMagnet

from app.core_api import select_workspace_owned

from .models import OfferLeadMagnet


async def reconcile_lead_magnets(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    offer_id: uuid.UUID,
    lead_magnet_ids: list[uuid.UUID],
) -> None:
    """Validate before changing associations; retain existing order and bonus metadata."""
    selected_ids = set(lead_magnet_ids)
    result = await db.execute(
        select_workspace_owned(LeadMagnet, workspace_id, LeadMagnet.id.in_(selected_ids))
    )
    found_ids = {magnet.id for magnet in result.scalars().all()}
    if selected_ids - found_ids:
        raise HTTPException(status_code=404, detail="Lead magnets not found in this workspace")

    association_result = await db.execute(
        select(OfferLeadMagnet).where(OfferLeadMagnet.offer_id == offer_id)
    )
    associations = association_result.scalars().all()
    existing_ids = {association.lead_magnet_id for association in associations}
    max_order = max((association.sort_order for association in associations), default=0)
    for association in associations:
        if association.lead_magnet_id not in selected_ids:
            await db.delete(association)
    for magnet_id in dict.fromkeys(lead_magnet_ids):
        if magnet_id not in existing_ids:
            max_order += 1
            db.add(
                OfferLeadMagnet(
                    offer_id=offer_id,
                    lead_magnet_id=magnet_id,
                    sort_order=max_order,
                    is_bonus=True,
                )
            )
