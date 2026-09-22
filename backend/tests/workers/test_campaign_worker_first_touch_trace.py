"""Integration test: autonomous first-touch sends record a decision/trace.

When the workspace autonomy mandate has ``auto_send_first_touches`` on, the
campaign worker sends the opener on the mandate's authority (no human approval).
Each such send must persist one :class:`MessageTrace` row so a bad opener stays
explainable (and is training data) after the fact.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal, engine
from app.models.campaign import (
    Campaign,
    CampaignContact,
    CampaignContactStatus,
    CampaignStatus,
    CampaignType,
)
from app.models.contact import Contact
from app.models.conversation import (
    Conversation,
    Message,
    MessageChannel,
    MessageDirection,
    MessageStatus,
)
from app.models.message_trace import MessageTrace
from app.models.phone_number import PhoneNumber
from app.models.workspace import Workspace
from app.workers.campaign_worker import CampaignWorker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
async def _fresh_engine_pool():
    await engine.dispose()
    yield
    await engine.dispose()


async def _persisting_send(db, *, workspace_id: uuid.UUID, contact_id: int):
    """Return a fake provider whose send_message persists a real iMessage Message."""

    async def _send_message(**kwargs):
        conversation = Conversation(
            workspace_id=workspace_id,
            contact_id=contact_id,
            workspace_phone="+18885550197",
            contact_phone=kwargs["to_number"],
            channel="imessage",
        )
        db.add(conversation)
        await db.flush()
        message = Message(
            conversation_id=conversation.id,
            idempotency_key=kwargs.get("idempotency_key") or uuid.uuid4(),
            direction=MessageDirection.OUTBOUND,
            channel=MessageChannel.IMESSAGE,
            body=kwargs["body"],
            status=MessageStatus.SENT,
            provider_message_id=f"mac-relay:{uuid.uuid4()}",
        )
        db.add(message)
        await db.flush()
        return message

    provider = AsyncMock()
    provider.send_message = AsyncMock(side_effect=_send_message)
    provider.close = AsyncMock()
    return provider


async def test_autonomy_first_touch_records_message_trace() -> None:
    worker = CampaignWorker()
    async with AsyncSessionLocal() as db:
        ws = Workspace(
            id=uuid.uuid4(),
            name="Trace",
            slug=f"trace-{uuid.uuid4().hex[:8]}",
            autonomy_mandate={"enabled": True, "auto_send_first_touches": True},
        )
        db.add(ws)
        await db.flush()

        contact = Contact(
            workspace_id=ws.id,
            first_name="Ava",
            phone_number="+14155550100",
            source="ad_library",
        )
        db.add(contact)
        await db.flush()

        campaign = Campaign(
            workspace_id=ws.id,
            name="Autopilot opener",
            description="Assistant-created draft from intent: Autopilot: outreach",
            campaign_type=CampaignType.SMS,
            status=CampaignStatus.RUNNING,
            from_phone_number="+18885550197",
            initial_message="Hi {first_name}, still running paid social ads?",
            ai_enabled=True,
        )
        db.add(campaign)
        await db.flush()

        cc = CampaignContact(
            campaign_id=campaign.id,
            contact_id=contact.id,
            status=CampaignContactStatus.PENDING,
        )
        db.add(cc)
        await db.flush()

        from_phone = PhoneNumber(
            workspace_id=ws.id,
            phone_number="+18885550197",
            mac_relay_sender_id="prestyj-demo-imessage",
            imessage_enabled=True,
            mac_relay_service="imessage",
            sms_enabled=True,
            is_active=True,
        )

        provider = await _persisting_send(db, workspace_id=ws.id, contact_id=contact.id)

        worker.rate_limiter.check_campaign_rate_limit = AsyncMock(return_value=True)
        worker.number_pool.peek_next_available_number = AsyncMock(return_value=from_phone)
        worker.number_pool.reserve_number_for_send = AsyncMock(return_value=True)
        worker.compliance_service.evaluate = AsyncMock(
            return_value=MagicMock(allowed=True, reason=None)
        )
        worker.compliance_service.apply_suppression = MagicMock()
        worker.reputation_tracker.increment_sent = AsyncMock()
        worker._get_text_provider = MagicMock(return_value=provider)  # type: ignore[method-assign]

        await worker._process_initial_messages(campaign, {}, db, worker.logger)
        await db.commit()

        traces = (
            (await db.execute(select(MessageTrace).where(MessageTrace.workspace_id == ws.id)))
            .scalars()
            .all()
        )
        assert len(traces) == 1
        trace = traces[0]
        assert trace.generated_text == "Hi Ava, still running paid social ads?"
        assert trace.mandate["authorized_rule"] == "act_and_report.first_touch"
        assert trace.mandate["auto_send_first_touches"] is True
        assert trace.message_id is not None
        assert trace.conversation_state["channel"] == "imessage"

        # Idempotent: re-running the tick must not double-record (the contact is
        # already SENT, so no second opener and no second trace).
        await worker._process_initial_messages(campaign, {}, db, worker.logger)
        await db.commit()
        count = (
            (await db.execute(select(MessageTrace).where(MessageTrace.workspace_id == ws.id)))
            .scalars()
            .all()
        )
        assert len(count) == 1


async def test_mandate_off_records_no_trace() -> None:
    worker = CampaignWorker()
    async with AsyncSessionLocal() as db:
        ws = Workspace(
            id=uuid.uuid4(),
            name="NoTrace",
            slug=f"notrace-{uuid.uuid4().hex[:8]}",
            autonomy_mandate={"enabled": False, "auto_send_first_touches": False},
        )
        db.add(ws)
        await db.flush()

        contact = Contact(
            workspace_id=ws.id,
            first_name="Sam",
            phone_number="+14155550101",
            source="ad_library",
        )
        db.add(contact)
        await db.flush()

        campaign = Campaign(
            workspace_id=ws.id,
            name="Manual opener",
            campaign_type=CampaignType.SMS,
            status=CampaignStatus.RUNNING,
            from_phone_number="+18885550197",
            initial_message="Hi {first_name}",
            ai_enabled=True,
        )
        db.add(campaign)
        await db.flush()

        db.add(
            CampaignContact(
                campaign_id=campaign.id,
                contact_id=contact.id,
                status=CampaignContactStatus.PENDING,
            )
        )
        await db.flush()

        from_phone = PhoneNumber(
            workspace_id=ws.id,
            phone_number="+18885550197",
            imessage_enabled=True,
            mac_relay_sender_id="x",
            mac_relay_service="imessage",
            sms_enabled=True,
            is_active=True,
        )
        provider = await _persisting_send(db, workspace_id=ws.id, contact_id=contact.id)

        worker.rate_limiter.check_campaign_rate_limit = AsyncMock(return_value=True)
        worker.number_pool.peek_next_available_number = AsyncMock(return_value=from_phone)
        worker.number_pool.reserve_number_for_send = AsyncMock(return_value=True)
        worker.compliance_service.evaluate = AsyncMock(
            return_value=MagicMock(allowed=True, reason=None)
        )
        worker.compliance_service.apply_suppression = MagicMock()
        worker.reputation_tracker.increment_sent = AsyncMock()
        worker._get_text_provider = MagicMock(return_value=provider)  # type: ignore[method-assign]

        await worker._process_initial_messages(campaign, {}, db, worker.logger)
        await db.commit()

        traces = (
            (await db.execute(select(MessageTrace).where(MessageTrace.workspace_id == ws.id)))
            .scalars()
            .all()
        )
        assert traces == []
