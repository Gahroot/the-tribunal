"""Campaign filtering engine - shared query builder for campaign listing."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select

from app.models.campaign import Campaign


def apply_campaign_filters(
    query: Select[Any],
    workspace_id: uuid.UUID,
    *,
    status: str | None = None,
    campaign_type: str | None = None,
    agent_id: uuid.UUID | None = None,
    offer_id: uuid.UUID | None = None,
    name: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
) -> Select[Any]:
    """Apply campaign filters to a SQLAlchemy query.

    Single source of truth for campaign list filtering. Always scopes the
    query to ``workspace_id``.
    """
    query = query.where(Campaign.workspace_id == workspace_id)

    if status:
        query = query.where(Campaign.status == status)
    if campaign_type:
        query = query.where(Campaign.campaign_type == campaign_type)
    if agent_id is not None:
        query = query.where(Campaign.agent_id == agent_id)
    if offer_id is not None:
        query = query.where(Campaign.offer_id == offer_id)

    if name:
        query = query.where(Campaign.name.ilike(f"%{name}%"))

    if created_after:
        query = query.where(Campaign.created_at >= created_after)
    if created_before:
        query = query.where(Campaign.created_at <= created_before)
    if started_after:
        query = query.where(Campaign.started_at >= started_after)
    if started_before:
        query = query.where(Campaign.started_at <= started_before)

    return query
