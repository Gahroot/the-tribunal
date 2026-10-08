"""Conservative, durable reply attribution for existing message-test enrollments."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignContact
from app.models.contact import Contact
from app.models.conversation import (
    Conversation,
    Message,
    MessageChannel,
    MessageDirection,
    MessageStatus,
)
from app.models.message_test import MessageTest, TestContact, TestContactStatus, TestVariant


async def attribute_message_test_reply(
    db: AsyncSession, message: Message, workspace_id: uuid.UUID, log: Any
) -> bool:
    """Count one real responding contact, not messages or provider deliveries.

    A conversation must identify exactly one sent enrollment in this workspace.
    Do not guess between experiments or a campaign sharing the same thread.
    The existing last_reply_at marker and locked parent counters are committed
    together, so retries (including concurrent ones) cannot inflate rates.
    """
    if (
        message.direction != MessageDirection.INBOUND
        or message.channel not in (MessageChannel.SMS, MessageChannel.IMESSAGE)
        or message.status != MessageStatus.RECEIVED
        or not message.body.strip()
        or message.created_at is None
    ):
        return False

    rows = (
        await db.execute(
            select(TestContact, MessageTest)
            .join(MessageTest, TestContact.message_test_id == MessageTest.id)
            .join(Conversation, TestContact.conversation_id == Conversation.id)
            .join(Contact, TestContact.contact_id == Contact.id)
            .where(
                Conversation.id == message.conversation_id,
                Conversation.workspace_id == workspace_id,
                Contact.workspace_id == workspace_id,
                Conversation.contact_id == TestContact.contact_id,
                MessageTest.workspace_id == workspace_id,
                TestContact.first_sent_at <= message.created_at,
            )
            .order_by(MessageTest.id, TestContact.id)
            .with_for_update(of=(MessageTest, TestContact))
            .execution_options(populate_existing=True)
        )
    ).all()
    if len(rows) != 1:
        if rows:
            log.info("message_test_reply_ambiguous", conversation_id=str(message.conversation_id))
        return False
    enrollment, test = rows[0]
    if enrollment.last_reply_at is not None or enrollment.status not in (
        TestContactStatus.SENT,
        TestContactStatus.DELIVERED,
    ):
        return False

    campaign_id = await db.scalar(
        select(CampaignContact.id)
        .join(Campaign, CampaignContact.campaign_id == Campaign.id)
        .where(
            CampaignContact.conversation_id == message.conversation_id,
            CampaignContact.contact_id == enrollment.contact_id,
            Campaign.workspace_id == workspace_id,
            CampaignContact.first_sent_at <= message.created_at,
        )
        .limit(1)
    )
    if campaign_id is not None:
        log.info("message_test_reply_ambiguous", conversation_id=str(message.conversation_id))
        return False

    variant = await db.scalar(
        select(TestVariant)
        .where(TestVariant.id == enrollment.variant_id, TestVariant.message_test_id == test.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if variant is None:
        return False

    enrollment.status = TestContactStatus.REPLIED
    enrollment.last_reply_at = message.created_at
    test.replies_received += 1
    variant.replies_received += 1
    # Match analytics' sent-contact denominator; replies do not imply qualification.
    variant.update_rates()
    await db.commit()
    log.info(
        "message_test_reply_attributed",
        test_id=str(test.id),
        variant_id=str(variant.id),
        message_id=str(message.id),
    )
    return True
