"""Workspace-scoped, attempt-level voice campaign funnel.

Attempts are ordered by call creation within a campaign/contact. Hours are UTC;
costs are estimates, not provider invoices. Only outcomes linked to the call
message count toward qualification and appointments.
"""

import uuid
from datetime import datetime

from sqlalchemy import Integer, and_, case, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.appointment import Appointment, AppointmentStatus
from app.models.call_outcome import CallOutcome, OutcomeType
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import (
    Conversation,
    Message,
    MessageChannel,
    MessageDirection,
    MessageStatus,
)


def _attempts(workspace_id: uuid.UUID, campaign_id: uuid.UUID | None = None):
    """One row per initiated outbound voice message, including old attempts."""
    appointment_booked = exists().where(
        Appointment.message_id == Message.id,
        Appointment.workspace_id == workspace_id,
    )
    appointment_shown = exists().where(
        Appointment.message_id == Message.id,
        Appointment.workspace_id == workspace_id,
        Appointment.status == AppointmentStatus.COMPLETED,
    )
    connected = and_(
        Message.status == MessageStatus.COMPLETED,
        (CallOutcome.outcome_type.is_(None))
        | CallOutcome.outcome_type.in_(
            [OutcomeType.COMPLETED, OutcomeType.APPOINTMENT_BOOKED, OutcomeType.LEAD_QUALIFIED]
        ),
    )
    query = (
        select(
            Message.created_at.label("called_at"),
            Message.campaign_id.label("campaign_id"),
            Campaign.name.label("campaign_name"),
            func.coalesce(Contact.source, literal("Unknown")).label("source"),
            func.row_number()
            .over(
                partition_by=(Message.campaign_id, Conversation.contact_id),
                order_by=(Message.created_at, Message.id),
            )
            .label("attempt_number"),
            case((connected, 1), else_=0).label("connected"),
            case(
                (
                    connected & (func.length(func.trim(func.coalesce(Message.transcript, ""))) > 0),
                    1,
                ),
                else_=0,
            ).label("conversation"),
            case(
                (
                    (CallOutcome.outcome_type == OutcomeType.LEAD_QUALIFIED)
                    | (CallOutcome.signals["lead_qualified"].astext == "true"),
                    1,
                ),
                else_=0,
            ).label("qualified"),
            case((appointment_booked, 1), else_=0).label("booked"),
            case((appointment_shown, 1), else_=0).label("shown"),
        )
        .join(
            Campaign,
            and_(Campaign.id == Message.campaign_id, Campaign.workspace_id == workspace_id),
        )
        .join(
            Conversation,
            and_(
                Conversation.id == Message.conversation_id,
                Conversation.workspace_id == workspace_id,
            ),
        )
        .join(
            Contact,
            and_(Contact.id == Conversation.contact_id, Contact.workspace_id == workspace_id),
        )
        .outerjoin(CallOutcome, CallOutcome.message_id == Message.id)
        .where(
            Message.channel == MessageChannel.VOICE,
            Message.direction == MessageDirection.OUTBOUND,
            Message.status.notin_([MessageStatus.QUEUED, MessageStatus.SENDING]),
        )
    )
    if campaign_id is not None:
        query = query.where(Campaign.id == campaign_id)
    return query.subquery()


def _metrics(row) -> dict:
    calls = int(row.calls or 0)
    connected = int(row.connected or 0)
    conversations = int(row.conversation or 0)
    qualified = int(row.qualified or 0)
    booked = int(row.booked or 0)
    shown = int(row.shown or 0)
    cost = round(calls * settings.ai_cost_per_call_usd, 2)
    return {
        "calls": calls,
        "connected": connected,
        "conversations": conversations,
        "qualified": qualified,
        "booked": booked,
        "shown": shown,
        "connect_rate": round(connected / calls, 4) if calls else 0,
        "conversation_rate": round(conversations / calls, 4) if calls else 0,
        "qualified_rate": round(qualified / calls, 4) if calls else 0,
        "booked_rate": round(booked / calls, 4) if calls else 0,
        "shown_rate": round(shown / calls, 4) if calls else 0,
        "show_rate_of_booked": round(shown / booked, 4) if booked else None,
        "estimated_cost_usd": cost,
        "estimated_cost_per_call_usd": round(settings.ai_cost_per_call_usd, 2),
        "estimated_cost_per_booked_usd": round(cost / booked, 2) if booked else None,
        "estimated_cost_per_shown_usd": round(cost / shown, 2) if shown else None,
    }


async def get_attempt_funnel(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    starts_at: datetime,
    ends_at: datetime,
    campaign_id: uuid.UUID | None = None,
) -> dict:
    """Aggregate calls in [starts_at, ends_at) by four independent dimensions."""
    attempts = _attempts(workspace_id, campaign_id)
    hour = func.extract("hour", attempts.c.called_at.op("AT TIME ZONE")("UTC")).cast(Integer)
    dimensions = {
        "attempt": attempts.c.attempt_number,
        "hour_utc": hour,
        "lead_source": attempts.c.source,
        "campaign": attempts.c.campaign_id,
    }
    result = {}
    for name, dimension in [("overall", None), *dimensions.items()]:
        cols = [
            func.count().label("calls"),
            func.sum(attempts.c.connected).label("connected"),
            func.sum(attempts.c.conversation).label("conversation"),
            func.sum(attempts.c.qualified).label("qualified"),
            func.sum(attempts.c.booked).label("booked"),
            func.sum(attempts.c.shown).label("shown"),
        ]
        if dimension is not None:
            cols.insert(0, dimension.label("dimension"))
        if name == "campaign":
            cols.insert(1, func.max(attempts.c.campaign_name).label("campaign_name"))
        query = select(*cols).where(
            attempts.c.called_at >= starts_at, attempts.c.called_at < ends_at
        )
        if dimension is not None:
            query = query.group_by(dimension).order_by(dimension)
        rows = (await db.execute(query)).all()
        if dimension is None:
            result[name] = _metrics(rows[0])
        else:
            result[name] = [
                {
                    "value": str(row.dimension) if name == "campaign" else row.dimension,
                    **({"campaign_name": row.campaign_name} if name == "campaign" else {}),
                    **_metrics(row),
                }
                for row in rows
            ]
    return {
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "hour_timezone": "UTC",
        "cost_basis": "estimated_blended_ai_call_usd",
        **result,
    }
