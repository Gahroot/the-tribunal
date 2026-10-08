"""RF-007: exercise real shared worker dispatch with isolated in-memory campaigns."""

from datetime import UTC, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.models.campaign import CampaignStatus, CampaignType
from app.services.campaigns.campaign_lifecycle import resume_campaign, start_campaign
from app.services.campaigns.sending_window import has_scheduled_start_arrived
from app.workers.campaign_worker import CampaignWorker
from app.workers.voice_campaign_worker import VoiceCampaignWorker
from tests.factories import CampaignFactory

START = datetime(2026, 10, 9, 9, tzinfo=ZoneInfo("America/New_York"))


@pytest.mark.parametrize("offset", [-1, 0, 1])
@pytest.mark.parametrize(
    "start", [START, START.astimezone(UTC), START.astimezone(UTC).replace(tzinfo=None)]
)
def test_start_is_an_inclusive_utc_instant(offset, start):
    campaign = CampaignFactory.build(scheduled_start=start)
    now = START.astimezone(UTC) + timedelta(seconds=offset)
    assert has_scheduled_start_arrived(campaign, now) is (offset >= 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_class", [CampaignWorker, VoiceCampaignWorker])
@pytest.mark.parametrize("transition", ["start", "resume", "restart"])
@pytest.mark.parametrize("offset", [-1, 0, 1])
async def test_dispatch_waits_until_start(worker_class, transition, offset):
    campaign = CampaignFactory.build(
        campaign_type=(
            CampaignType.VOICE_SMS_FALLBACK
            if worker_class is VoiceCampaignWorker
            else CampaignType.SMS
        ),
        status=CampaignStatus.PAUSED if transition == "resume" else CampaignStatus.DRAFT,
        scheduled_start=START,
        scheduled_end=START + timedelta(days=1),
        sending_hours_start=time(9),
        sending_hours_end=time(17),
        sending_days=[4],
        timezone="America/New_York",
    )
    db = AsyncMock()
    eligibility_service = MagicMock()
    eligibility_service.evaluate_campaign = AsyncMock(
        return_value=MagicMock(
            eligible_count=1,
            already_contacted_count=0,
            selected_count=1,
            exclusions=[],
            deferral_label=None,
        )
    )
    if transition != "restart":
        with (
            patch("app.services.campaigns.campaign_lifecycle.datetime") as clock,
            # Readiness is covered through the API; this test isolates scheduled dispatch.
            patch(
                "app.services.campaigns.campaign_lifecycle._validate_voice_readiness",
                new=AsyncMock(),
            ),
            patch("app.services.campaigns.sending_window.datetime") as schedule_clock,
        ):
            clock.now.return_value = START.astimezone(UTC) - timedelta(days=1)
            schedule_clock.now.return_value = clock.now.return_value
            action = resume_campaign if transition == "resume" else start_campaign
            result = await action(
                db, campaign, contact_count=1, eligibility_service=eligibility_service
            )
        assert "Campaign scheduled; no sends before" in result.message
    else:
        # A newly constructed worker reads a persisted RUNNING campaign after restart.
        campaign.status = CampaignStatus.RUNNING
    assert campaign.status == CampaignStatus.RUNNING
    worker = worker_class()
    now = START.astimezone(UTC) + timedelta(seconds=offset)
    # Observe the dispatch boundary at/after start without sending any real traffic.
    worker._process_campaign_contacts = AsyncMock()
    with (
        patch("app.workers.base_campaign_worker.datetime") as clock,
        patch("app.workers.base_campaign_worker.settings") as settings,
        patch("app.workers.campaign_worker.get_text_message_provider") as sms_provider,
        patch("app.workers.voice_campaign_worker.TelnyxVoiceService") as voice_provider,
    ):
        clock.now.return_value = now
        settings.telnyx_api_key = "isolated-test-key"
        if offset < 0:
            # Before start, exercise the real subclass (including service construction).
            del worker._process_campaign_contacts
            await worker._process_campaign(campaign, db)
            sms_provider.assert_not_called()
            voice_provider.assert_not_called()
            db.execute.assert_not_awaited()
            db.commit.assert_not_awaited()
        else:
            await worker._process_campaign(campaign, db)
            worker._process_campaign_contacts.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_class", [CampaignWorker, VoiceCampaignWorker])
async def test_start_gate_does_not_bypass_daily_window(worker_class):
    campaign = CampaignFactory.build(
        scheduled_start=START,
        scheduled_end=None,
        sending_hours_start=time(10),
        sending_hours_end=time(17),
        sending_days=[4],
        timezone="America/New_York",
    )
    worker = worker_class()
    worker._process_campaign_contacts = AsyncMock()
    with patch("app.workers.base_campaign_worker.datetime") as clock:
        clock.now.return_value = START.astimezone(UTC)
        await worker._process_campaign(campaign, AsyncMock())
    worker._process_campaign_contacts.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_end_completes_even_before_future_start():
    campaign = CampaignFactory.build(
        status=CampaignStatus.RUNNING,
        scheduled_start=START + timedelta(days=1),
        scheduled_end=START.astimezone(UTC).replace(tzinfo=None) - timedelta(seconds=1),
    )
    worker = CampaignWorker()
    worker._process_campaign_contacts = AsyncMock()
    db = AsyncMock()
    report_service = MagicMock()
    report_service.generate_report = AsyncMock()
    with (
        patch("app.workers.base_campaign_worker.datetime") as clock,
        patch(
            "app.workers.base_campaign_worker.CampaignReportService", return_value=report_service
        ),
    ):
        clock.now.return_value = START.astimezone(UTC)
        await worker._process_campaign(campaign, db)
    report_service.generate_report.assert_awaited_once_with(db, campaign.id)
    assert campaign.status == CampaignStatus.COMPLETED
    worker._process_campaign_contacts.assert_not_awaited()
    db.commit.assert_awaited_once()
