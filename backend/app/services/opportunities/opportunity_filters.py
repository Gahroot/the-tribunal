"""Opportunity filtering engine - shared by opportunities API and future segmentation."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select

from app.models.opportunity import Opportunity


def apply_opportunity_filters(  # noqa: PLR0912
    query: Select[Any],
    workspace_id: uuid.UUID,
    *,
    pipeline_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    status: str | None = None,
    is_active: bool | None = None,
    source: str | None = None,
    search: str | None = None,
    value_min: Decimal | float | None = None,
    value_max: Decimal | float | None = None,
    probability_min: int | None = None,
    probability_max: int | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> Select[Any]:
    """Apply opportunity filters to a SQLAlchemy query.

    Single source of truth for opportunity filtering. Callers pass a base
    ``select(Opportunity)`` and receive a narrowed query.
    """
    query = query.where(Opportunity.workspace_id == workspace_id)

    if pipeline_id is not None:
        query = query.where(Opportunity.pipeline_id == pipeline_id)
    if stage_id is not None:
        query = query.where(Opportunity.stage_id == stage_id)
    if owner_id is not None:
        query = query.where(Opportunity.assigned_user_id == owner_id)
    if status is not None:
        query = query.where(Opportunity.status == status)
    if is_active is not None:
        query = query.where(Opportunity.is_active == is_active)
    if source is not None:
        query = query.where(Opportunity.source == source)
    if search:
        query = query.where(Opportunity.name.ilike(f"%{search}%"))

    if value_min is not None:
        query = query.where(Opportunity.amount >= value_min)
    if value_max is not None:
        query = query.where(Opportunity.amount <= value_max)

    if probability_min is not None:
        query = query.where(Opportunity.probability >= probability_min)
    if probability_max is not None:
        query = query.where(Opportunity.probability <= probability_max)

    if created_after is not None:
        query = query.where(Opportunity.created_at >= created_after)
    if created_before is not None:
        query = query.where(Opportunity.created_at <= created_before)

    return query
