"""RF-016: real persisted inbound text -> experiment outcomes, disposable SQL only."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.schema import CreateTable

from app.api.webhooks import mac_relay_handlers, telnyx_message_handlers
from app.core.config import settings
from app.models.campaign import Campaign, CampaignContact
from app.models.contact import Contact
from app.models.conversation import Message, MessageChannel
from app.models.drip_campaign import ResponseCategory
from app.models.message_test import MessageTest
from app.models.message_test import TestContact as Enrollment
from app.models.message_test import TestVariant as Variant
from app.models.phone_number import PhoneNumber
from app.services.message_tests.message_test_service import MessageTestService
from app.services.message_tests.reply_attribution import attribute_message_test_reply
from app.services.telephony import inbound_text
from tests.integration import test_inbox_postgres
from tests.integration.test_inbox_postgres import (
    OTHER_WORKSPACE,
    WORKSPACE,
    thread,
)

inbox_db = test_inbox_postgres.db
pytestmark = pytest.mark.integration
TABLES = (Campaign, CampaignContact, MessageTest, Variant, Enrollment, PhoneNumber)


@pytest.fixture
async def db(inbox_db: AsyncSession) -> AsyncIterator[AsyncSession]:
    connection = await inbox_db.connection()
    for model in TABLES:
        await connection.execute(CreateTable(model.__table__, include_foreign_key_constraints=[]))
    await inbox_db.commit()
    yield inbox_db


async def seed(db: AsyncSession) -> tuple[MessageTest, list[Variant], list[Enrollment]]:
    test = MessageTest(
        workspace_id=WORKSPACE,
        name="RF-016 fixture",
        from_phone_number="+15550000000",
        status="running",
        total_contacts=4,
        total_variants=2,
        messages_sent=4,
    )
    db.add(test)
    db.add(PhoneNumber(workspace_id=WORKSPACE, phone_number="+15550000000"))
    await db.flush()
    variants = [
        Variant(
            message_test_id=test.id,
            name=name,
            message_template=name,
            messages_sent=2,
            contacts_assigned=2,
            sort_order=i,
            is_control=i == 0,
        )
        for i, name in enumerate(("A", "B"))
    ]
    db.add_all(variants)
    await db.flush()
    enrollments = []
    for i in range(1, 7):
        workspace = OTHER_WORKSPACE if i == 6 else WORKSPACE
        db.add(
            Contact(
                id=i, workspace_id=workspace, first_name="Fixture", phone_number=f"+1555{i:07d}"
            )
        )
        conversation = thread(
            i, contact_id=i, workspace_id=workspace, assigned_agent_id=uuid4(), ai_enabled=False
        )
        db.add(conversation)
        if i <= 4:
            enrollment = Enrollment(
                message_test_id=test.id,
                variant_id=variants[(i - 1) % 2].id,
                contact_id=i,
                conversation_id=conversation.id,
                status="sent",
                first_sent_at=datetime.now(UTC) - timedelta(minutes=1),
            )
            db.add(enrollment)
            enrollments.append(enrollment)
    await db.commit()
    return test, variants, enrollments


@contextmanager
def no_external_effects():
    """Keep ingestion, attribution and campaign routing real; prohibit outreach."""
    with (
        patch.object(inbound_text, "_pause_drip_enrollments", AsyncMock()),
        patch.object(inbound_text, "_send_push_notification", AsyncMock()),
        patch(
            "app.services.calendar.confirmation_reply.handle_confirmation_reply",
            AsyncMock(return_value=False),
        ),
    ):
        yield


async def receive(
    db: AsyncSession, index: int, delivery: str, *, workspace=WORKSPACE, channel=MessageChannel.SMS
) -> Message:
    event = inbound_text.InboundTextEvent(
        provider_message_id=delivery,
        from_number=f"+1555{index:07d}",
        to_number="+15550000000",
        body="Please send the details",
        workspace_id=workspace,
        channel=channel,
    )

    async def persist(db, event):
        return await inbound_text.persist_inbound_text_message(
            db=db,
            provider_message_id=event.provider_message_id,
            from_number=event.from_number,
            to_number=event.to_number,
            body=event.body,
            workspace_id=event.workspace_id,
            channel=event.channel,
            log=structlog.get_logger(),
        )

    with no_external_effects():
        result = await inbound_text.process_inbound_text_event(
            db=db,
            event=event,
            log=structlog.get_logger(),
            ingest_message=persist,
            command_processor=type(
                "FixtureCommands",
                (),
                {
                    "try_process_command": AsyncMock(return_value=False),
                },
            )(),
            check_operator_fn=AsyncMock(return_value=None),
        )
    assert result is not None
    return result


@pytest.mark.asyncio
async def test_variants_duplicate_and_analytics(db: AsyncSession) -> None:
    test, variants, enrollments = await seed(db)
    first = await receive(db, 1, "rf016-a")
    second = await receive(db, 2, "rf016-b", channel=MessageChannel.IMESSAGE)
    assert (await receive(db, 1, "rf016-a")).id == first.id
    assert (await receive(db, 2, "rf016-b", channel=MessageChannel.IMESSAGE)).id == second.id
    await receive(db, 1, "rf016-a-followup")  # A second message isn't a second responder.
    analytics = await MessageTestService(db).get_analytics(test.id, WORKSPACE)
    assert analytics.replies_received == 2 and analytics.overall_response_rate == 50
    assert [
        (v.replies_received, v.response_rate, v.qualification_rate) for v in analytics.variants
    ] == [(1, 50, 0), (1, 50, 0)]
    assert analytics.contacts_qualified == 0
    assert analytics.winning_variant_id is None and not analytics.statistical_significance
    await db.refresh(enrollments[0])
    assert enrollments[0].status == "replied" and enrollments[0].last_reply_at == first.created_at
    assert await db.scalar(select(func.count(Message.id))) == 3

    # A later send changes the denominator; the existing send primitive must
    # continue to derive rates from the newly attributed reply count.
    variants[0].messages_sent += 1
    variants[0].update_rates()
    test.messages_sent += 1
    await db.commit()
    updated = await MessageTestService(db).get_analytics(test.id, WORKSPACE)
    assert updated.overall_response_rate == 40
    assert updated.variants[0].response_rate == pytest.approx(100 / 3)


@pytest.mark.asyncio
async def test_unrelated_scope_ambiguous_and_unsent(db: AsyncSession) -> None:
    test, variants, enrollments = await seed(db)
    await receive(db, 5, "unrelated")
    await receive(db, 6, "other-workspace", workspace=OTHER_WORKSPACE)
    # Inconsistent tenant rows must not be counted even with a stored thread ID.
    test.workspace_id = OTHER_WORKSPACE
    await db.commit()
    await receive(db, 1, "cross-workspace-test")
    test.workspace_id = WORKSPACE
    # Two existing sent tests in one thread have no unambiguous result.
    other = MessageTest(
        workspace_id=WORKSPACE,
        name="Overlapping test",
        from_phone_number="+15550000000",
        status="running",
    )
    db.add(other)
    await db.flush()
    db.add(
        Enrollment(
            message_test_id=other.id,
            contact_id=2,
            conversation_id=enrollments[1].conversation_id,
            first_sent_at=enrollments[1].first_sent_at,
            status="sent",
        )
    )
    enrollments[2].first_sent_at = datetime.now(UTC) + timedelta(days=1)
    enrollments[3].variant_id = None
    await db.commit()
    await receive(db, 2, "ambiguous")
    await receive(db, 3, "before-send")
    await receive(db, 4, "missing-variant")
    result = await MessageTestService(db).get_analytics(test.id, WORKSPACE)
    assert result.replies_received == 0 and result.overall_response_rate == 0
    assert all(v.replies_received == 0 and v.response_rate == 0 for v in result.variants)


@pytest.mark.asyncio
async def test_retry_recovers_ingested_message(db: AsyncSession) -> None:
    test, _, _ = await seed(db)
    with (
        patch(
            "app.services.message_tests.reply_attribution.attribute_message_test_reply",
            AsyncMock(side_effect=RuntimeError("fixture interrupted outcome write")),
        ),
        pytest.raises(RuntimeError, match="interrupted"),
    ):
        await receive(db, 1, "retry-after-ingestion")
    assert await db.scalar(select(func.count(Message.id))) == 1
    await receive(db, 1, "retry-after-ingestion")
    assert (await MessageTestService(db).get_analytics(test.id, WORKSPACE)).replies_received == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["telnyx", "mac-relay"])
async def test_provider_handler_retry_recovers_outcome(db: AsyncSession, provider: str) -> None:
    test, _, _ = await seed(db)
    handler = telnyx_message_handlers if provider == "telnyx" else mac_relay_handlers
    call = (
        handler.handle_inbound_message if provider == "telnyx" else handler.handle_mac_relay_message
    )
    payload = (
        {
            "id": "provider-retry",
            "from": {"phone_number": "+15550000001"},
            "to": [{"phone_number": "+15550000000"}],
            "text": "Please send details",
        }
        if provider == "telnyx"
        else {
            "guid": "provider-retry",
            "from": "+15550000001",
            "to": "+15550000000",
            "text": "Please send details",
            "is_from_me": False,
        }
    )

    @asynccontextmanager
    async def session():
        yield db

    with (
        no_external_effects(),
        patch.object(handler, "AsyncSessionLocal", session),
        patch.object(settings, "telnyx_api_key", "fixture-no-delivery"),
        patch.object(
            inbound_text.command_processor_service,
            "try_process_command",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.services.telephony.telnyx.TelnyxSMSService.send_message",
            AsyncMock(side_effect=AssertionError("No fixture outreach")),
        ),
    ):
        with (
            patch(
                "app.services.message_tests.reply_attribution.attribute_message_test_reply",
                AsyncMock(side_effect=RuntimeError("fixture interruption")),
            ),
            pytest.raises(RuntimeError, match="interruption"),
        ):
            await call(payload, structlog.get_logger())
        await call(payload, structlog.get_logger())
        await call(payload, structlog.get_logger())
    assert await db.scalar(select(func.count(Message.id))) == 1
    result = await MessageTestService(db).get_analytics(test.id, WORKSPACE)
    assert result.replies_received == 1 and result.variants[0].replies_received == 1


@pytest.mark.asyncio
async def test_concurrent_reply_claims(db: AsyncSession) -> None:
    test, _, _ = await seed(db)
    with patch(
        "app.services.message_tests.reply_attribution.attribute_message_test_reply",
        AsyncMock(side_effect=RuntimeError("fixture interruption")),
    ):
        for index in (1, 2):
            with pytest.raises(RuntimeError, match="interruption"):
                await receive(db, index, f"concurrent-{index}")
    session_factory = async_sessionmaker(db.bind, expire_on_commit=False)

    async def claim(index):
        async with session_factory() as session:
            message = await session.scalar(
                select(Message).where(Message.provider_message_id == f"concurrent-{index}")
            )
            return await attribute_message_test_reply(
                session, message, WORKSPACE, structlog.get_logger()
            )

    results = await asyncio.gather(claim(1), claim(1), claim(2), claim(2))
    assert sum(results) == 2
    test_id = test.id
    db.expire_all()
    result = await MessageTestService(db).get_analytics(test_id, WORKSPACE)
    assert result.replies_received == 2
    assert [v.replies_received for v in result.variants] == [1, 1]


@pytest.mark.asyncio
async def test_campaign_reply_stays_campaign_only(db: AsyncSession) -> None:
    test, _, enrollments = await seed(db)
    campaign = Campaign(
        workspace_id=WORKSPACE,
        name="Existing campaign",
        ai_enabled=False,
        from_phone_number="+15550000000",
    )
    db.add(campaign)
    await db.flush()
    campaign_contact = CampaignContact(
        campaign_id=campaign.id,
        contact_id=1,
        status="sent",
        conversation_id=enrollments[0].conversation_id,
        first_sent_at=enrollments[0].first_sent_at,
        messages_sent=1,
    )
    db.add(campaign_contact)
    await db.commit()
    # Classification is the only external dependency: campaign query, duplicate
    # guard, state transitions and counters all run through the real pipeline.
    with patch(
        "app.services.campaigns.reply_handler.classify_response",
        AsyncMock(return_value=ResponseCategory.NOT_NOW),
    ):
        await receive(db, 1, "campaign-reply")
        await receive(db, 1, "campaign-reply")
    await db.refresh(campaign)
    await db.refresh(campaign_contact)
    assert campaign.replies_received == 1 and campaign_contact.messages_received == 1
    assert campaign_contact.status == "replied"
    result = await MessageTestService(db).get_analytics(test.id, WORKSPACE)
    assert result.replies_received == 0 and result.variants[0].response_rate == 0
