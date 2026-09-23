"""Booking wins over a failed Telnyx hangup when routing a campaign contact."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.campaign import Campaign, CampaignContact, CampaignContactStatus
from app.services.campaigns.cadence import sms_touch_pending
from app.services.campaigns.campaign_call_stats import update_campaign_call_stats


@pytest.mark.asyncio
async def test_successful_booking_never_requeues_or_sends_sms() -> None:
    campaign = Campaign(
        id=uuid4(),
        workspace_id=uuid4(),
        calls_answered=0,
        appointments_booked=0,
        sms_fallback_enabled=True,
        sms_fallback_template="Hi",
        messages_sent=0,
    )
    contact = CampaignContact(
        id=uuid4(),
        campaign=campaign,
        status=CampaignContactStatus.CALLING,
        call_attempts=1,
        call_duration_seconds=None,
        last_call_status=None,
        last_call_at=datetime.now(UTC),
        messages_sent=0,
        opted_out=False,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = contact
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()

    await update_campaign_call_stats(
        db, uuid4(), "no_answer", 10, "failed", MagicMock(), booking_outcome="success"
    )

    assert contact.status == CampaignContactStatus.CALL_ANSWERED
    assert contact.next_follow_up_at is None
    assert contact.last_call_status == "answered"
    assert not sms_touch_pending(campaign, contact)
    assert campaign.calls_answered == 1
    assert campaign.appointments_booked == 1
    db.commit.assert_awaited_once()
