"""Dry run: prove autonomy auto-sends Prestyj first-touches over iMessage.

Seeds the deterministic Prestyj Batch Video Ads workspace, then runs the two
workers that make up the autopilot first-touch path against the local DB with an
**in-process stub iMessage provider** (no external Mac relay required):

1. ``OutboundAutoDraftWorker`` — drafts a campaign from never-enrolled ad-library
   contacts and, because the workspace mandate has ``auto_send_first_touches`` on,
   launches it immediately (campaign goes RUNNING, no PendingAction parked).
2. ``CampaignWorker`` — sends the first-touch opener to each enrolled contact over
   the iMessage sender and records one MessageTrace per send.

Prints structured ``dryrun_*`` log lines plus a final JSON summary so
``.ezcoder/eyes/logs.sh`` can confirm the events and the row counts.

Run from ``backend/``::

    uv run python -m scripts.dev.autopilot_first_touch_dryrun
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import structlog
from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.campaign import Campaign, CampaignStatus
from app.models.contact import Contact
from app.models.conversation import (
    Conversation,
    Message,
    MessageChannel,
    MessageDirection,
    MessageStatus,
)
from app.models.message_trace import MessageTrace
from app.models.pending_action import PendingAction
from app.workers import campaign_worker as campaign_worker_module
from app.workers.campaign_worker import CampaignWorker
from app.workers.outbound_auto_draft_worker import LAUNCH_ACTION_TYPE, OutboundAutoDraftWorker

log = structlog.get_logger("autopilot_dryrun")


class _StubImessageProvider:
    """Persist a real iMessage Message without touching an external relay."""

    def __init__(self) -> None:
        self.sent = 0

    async def send_message(
        self,
        to_number: str,
        from_number: str,
        body: str,
        db: Any,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID | None = None,
        campaign_id: uuid.UUID | None = None,
        phone_number_id: uuid.UUID | None = None,
        idempotency_key: uuid.UUID | None = None,
    ) -> Message:
        contact = (
            (await db.execute(select(Contact).where(Contact.phone_number == to_number)))
            .scalars()
            .first()
        )
        conversation = Conversation(
            workspace_id=workspace_id,
            contact_id=contact.id if contact is not None else None,
            workspace_phone=str(from_number)[:20],
            contact_phone=str(to_number)[:20],
            channel="imessage",
            assigned_agent_id=agent_id,
        )
        db.add(conversation)
        await db.flush()
        message = Message(
            conversation_id=conversation.id,
            idempotency_key=idempotency_key or uuid.uuid4(),
            direction=MessageDirection.OUTBOUND,
            channel=MessageChannel.IMESSAGE,
            body=body,
            status=MessageStatus.SENT,
            provider_message_id=f"mac-relay:{uuid.uuid4()}",
        )
        db.add(message)
        await db.flush()
        self.sent += 1
        log.info("dryrun_stub_imessage_sent", to=to_number, from_=from_number, body=body)
        return message

    async def close(self) -> None:  # pragma: no cover - nothing to release
        return None


async def _counts(db: Any, workspace_id: uuid.UUID) -> dict[str, int]:
    async def _count(stmt: Any) -> int:
        return int((await db.execute(stmt)).scalar() or 0)

    return {
        "running_campaigns": await _count(
            select(func.count(Campaign.id)).where(
                Campaign.workspace_id == workspace_id,
                Campaign.status == CampaignStatus.RUNNING,
            )
        ),
        "pending_launch_actions": await _count(
            select(func.count(PendingAction.id)).where(
                PendingAction.workspace_id == workspace_id,
                PendingAction.action_type == LAUNCH_ACTION_TYPE,
                PendingAction.status == "pending",
            )
        ),
        "conversations": await _count(
            select(func.count(Conversation.id)).where(Conversation.workspace_id == workspace_id)
        ),
        "imessage_messages": await _count(
            select(func.count(Message.id))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.workspace_id == workspace_id,
                Message.channel == MessageChannel.IMESSAGE,
                Message.direction == MessageDirection.OUTBOUND,
            )
        ),
        "message_traces": await _count(
            select(func.count(MessageTrace.id)).where(MessageTrace.workspace_id == workspace_id)
        ),
    }


async def run() -> dict[str, Any]:
    from scripts.seed_prestyj import seed

    workspace, offer, agent, phone, contacts = await seed()
    log.info(
        "dryrun_seeded",
        workspace_id=str(workspace.id),
        offer_id=str(offer.id),
        phone=phone.phone_number,
        imessage_enabled=phone.imessage_enabled,
        ad_library_contacts=len(contacts),
    )

    # Force every send through the in-process stub (no external relay needed).
    stub = _StubImessageProvider()
    campaign_worker_module.get_text_message_provider = lambda *a, **k: stub  # type: ignore[assignment]

    draft_worker = OutboundAutoDraftWorker()
    await draft_worker._process_items()
    log.info("dryrun_auto_draft_complete")

    send_worker = CampaignWorker()
    # Neutralize Redis-backed gates so the dry run is deterministic offline.
    from unittest.mock import AsyncMock

    send_worker.rate_limiter.check_campaign_rate_limit = AsyncMock(return_value=True)
    send_worker.rate_limiter.check_and_increment_campaign_daily = AsyncMock(return_value=(True, 1))
    send_worker.number_pool.reserve_number_for_send = AsyncMock(return_value=True)
    send_worker.reputation_tracker.increment_sent = AsyncMock()
    await send_worker._process_items()
    log.info("dryrun_campaign_send_complete", stub_sent=stub.sent)

    # Second pass proves idempotency: no new opener, no new trace.
    await send_worker._process_items()

    async with AsyncSessionLocal() as db:
        summary = await _counts(db, workspace.id)
        summary["workspace_id"] = str(workspace.id)
        summary["stub_imessage_sent"] = stub.sent
        # Sample one trace to show the authorizing mandate rule + channel.
        trace = (
            await db.execute(
                select(MessageTrace).where(MessageTrace.workspace_id == workspace.id).limit(1)
            )
        ).scalar_one_or_none()
        if trace is not None:
            summary["sample_trace"] = {
                "authorized_rule": trace.mandate.get("authorized_rule"),
                "auto_send_first_touches": trace.mandate.get("auto_send_first_touches"),
                "channel": trace.conversation_state.get("channel"),
                "generated_text": trace.generated_text,
            }
    return summary


def main() -> None:
    summary = asyncio.run(run())
    log.info("dryrun_summary", **summary)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
