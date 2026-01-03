"""Campaign management endpoints."""

import uuid
from datetime import UTC, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.agent import Agent
from app.models.campaign import Campaign, CampaignContact, CampaignStatus
from app.models.contact import Contact
from app.models.workspace import Workspace
from app.schemas.campaign import (
    CampaignAnalytics,
    CampaignContactAdd,
    CampaignContactResponse,
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
    PaginatedCampaigns,
)

router = APIRouter()


def _parse_time_string(time_str: str | None) -> time | None:
    """Parse a time string like '09:00' into a datetime.time object."""
    if time_str is None:
        return None
    try:
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


@router.get("", response_model=PaginatedCampaigns)
async def list_campaigns(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status_filter: str | None = None,
) -> PaginatedCampaigns:
    """List campaigns in a workspace."""
    query = select(Campaign).where(Campaign.workspace_id == workspace_id)

    if status_filter:
        query = query.where(Campaign.status == status_filter)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(Campaign.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    campaigns = result.scalars().all()

    return PaginatedCampaigns(
        items=[CampaignResponse.model_validate(c) for c in campaigns],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    workspace_id: uuid.UUID,
    campaign_in: CampaignCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Campaign:
    """Create a new campaign."""
    # Verify agent if provided
    if campaign_in.agent_id:
        agent_result = await db.execute(
            select(Agent).where(
                Agent.id == campaign_in.agent_id,
                Agent.workspace_id == workspace_id,
            )
        )
        if not agent_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

    # Convert time strings to datetime.time objects
    campaign_data = campaign_in.model_dump()
    if "sending_hours_start" in campaign_data:
        campaign_data["sending_hours_start"] = _parse_time_string(
            campaign_data["sending_hours_start"]
        )
    if "sending_hours_end" in campaign_data:
        campaign_data["sending_hours_end"] = _parse_time_string(
            campaign_data["sending_hours_end"]
        )

    campaign = Campaign(
        workspace_id=workspace_id,
        **campaign_data,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    return campaign


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Campaign:
    """Get a campaign by ID."""
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.workspace_id == workspace_id,
        )
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return campaign


@router.put("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    campaign_in: CampaignUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Campaign:
    """Update a campaign."""
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.workspace_id == workspace_id,
        )
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    # Only allow updates on draft/paused campaigns
    if campaign.status not in ("draft", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only update draft or paused campaigns",
        )

    # Update fields
    update_data = campaign_in.model_dump(exclude_unset=True)

    # Convert time strings to datetime.time objects
    if "sending_hours_start" in update_data:
        update_data["sending_hours_start"] = _parse_time_string(
            update_data["sending_hours_start"]
        )
    if "sending_hours_end" in update_data:
        update_data["sending_hours_end"] = _parse_time_string(
            update_data["sending_hours_end"]
        )

    for field, value in update_data.items():
        setattr(campaign, field, value)

    await db.commit()
    await db.refresh(campaign)

    return campaign


@router.post("/{campaign_id}/start")
async def start_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, str]:
    """Start a campaign."""
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.workspace_id == workspace_id,
        )
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    if campaign.status not in ("draft", "paused", "scheduled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start campaign with status: {campaign.status}",
        )

    # Check if campaign has contacts
    count_result = await db.execute(
        select(func.count(CampaignContact.id)).where(
            CampaignContact.campaign_id == campaign_id
        )
    )
    contact_count = count_result.scalar() or 0

    if contact_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign has no contacts",
        )

    campaign.status = CampaignStatus.RUNNING.value
    campaign.started_at = datetime.now(UTC)
    await db.commit()

    return {"status": "running", "message": f"Campaign started with {contact_count} contacts"}


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, str]:
    """Pause a campaign."""
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.workspace_id == workspace_id,
        )
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    if campaign.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only pause running campaigns",
        )

    campaign.status = CampaignStatus.PAUSED.value
    await db.commit()

    return {"status": "paused"}


@router.post("/{campaign_id}/contacts", response_model=dict[str, int])
async def add_contacts(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    contacts_in: CampaignContactAdd,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, int]:
    """Add contacts to a campaign."""
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.workspace_id == workspace_id,
        )
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    if campaign.status not in ("draft", "paused"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only add contacts to draft or paused campaigns",
        )

    # Verify contacts belong to workspace
    contacts_result = await db.execute(
        select(Contact).where(
            Contact.id.in_(contacts_in.contact_ids),
            Contact.workspace_id == workspace_id,
        )
    )
    valid_contacts = contacts_result.scalars().all()
    valid_contact_ids = {c.id for c in valid_contacts}

    # Get existing campaign contacts
    existing_result = await db.execute(
        select(CampaignContact.contact_id).where(
            CampaignContact.campaign_id == campaign_id
        )
    )
    existing_ids = {row[0] for row in existing_result.all()}

    # Add new contacts
    added_count = 0
    for contact_id in valid_contact_ids:
        if contact_id not in existing_ids:
            campaign_contact = CampaignContact(
                campaign_id=campaign_id,
                contact_id=contact_id,
            )
            db.add(campaign_contact)
            added_count += 1

    # Update campaign stats
    campaign.total_contacts += added_count
    await db.commit()

    return {"added": added_count}


@router.get("/{campaign_id}/contacts", response_model=list[CampaignContactResponse])
async def list_campaign_contacts(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    status_filter: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[CampaignContactResponse]:
    """List contacts in a campaign."""
    # Verify campaign exists
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.workspace_id == workspace_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    query = select(CampaignContact).where(CampaignContact.campaign_id == campaign_id)

    if status_filter:
        query = query.where(CampaignContact.status == status_filter)

    query = query.order_by(CampaignContact.created_at.desc()).limit(limit)

    contacts_result = await db.execute(query)
    contacts = contacts_result.scalars().all()

    return [CampaignContactResponse.model_validate(c) for c in contacts]


@router.get("/{campaign_id}/analytics", response_model=CampaignAnalytics)
async def get_analytics(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> CampaignAnalytics:
    """Get campaign analytics."""
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.workspace_id == workspace_id,
        )
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    # Calculate rates
    reply_rate = 0.0
    if campaign.messages_sent > 0:
        reply_rate = (campaign.replies_received / campaign.messages_sent) * 100

    qualification_rate = 0.0
    if campaign.replies_received > 0:
        qualification_rate = (campaign.contacts_qualified / campaign.replies_received) * 100

    return CampaignAnalytics(
        total_contacts=campaign.total_contacts,
        messages_sent=campaign.messages_sent,
        messages_delivered=campaign.messages_delivered,
        messages_failed=campaign.messages_failed,
        replies_received=campaign.replies_received,
        contacts_qualified=campaign.contacts_qualified,
        contacts_opted_out=campaign.contacts_opted_out,
        reply_rate=reply_rate,
        qualification_rate=qualification_rate,
    )


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete a campaign."""
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.workspace_id == workspace_id,
        )
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    if campaign.status == "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete running campaign. Pause it first.",
        )

    await db.delete(campaign)
    await db.commit()
