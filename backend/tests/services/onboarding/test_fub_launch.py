"""RF-003: real creation/enrollment/lifecycle with fixture DB and compliance."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.agent import Agent
from app.models.campaign import Campaign, CampaignContact, CampaignStatus
from app.models.contact import Contact
from app.models.phone_number import PhoneNumber
from app.services.campaigns.recipient_eligibility import RecipientEligibility
from app.services.onboarding.fub_launch import launch_fub_campaign


@pytest.fixture
def launch_fixture(monkeypatch: pytest.MonkeyPatch):
    from app.services.onboarding import fub_launch

    ws = uuid.uuid4()
    agent = Agent(id=uuid.uuid4(), workspace_id=ws, name="Realtor Agent", is_active=True)
    phone = PhoneNumber(
        id=uuid.uuid4(),
        workspace_id=ws,
        phone_number="+15555550100",
        is_active=True,
        sms_enabled=True,
        imessage_enabled=False,
    )
    contacts = [
        Contact(id=i, workspace_id=ws, first_name="Fixture", phone_number=f"+155555501{i:02}")
        for i in (11, 12)
    ]
    added = []
    db = MagicMock()
    db.add.side_effect = added.append
    db.fixture_contacts = contacts

    async def flush():
        # Model column defaults are normally populated by INSERT.
        for obj in added:
            if isinstance(obj, Campaign) and obj.status is None:
                obj.status = CampaignStatus.DRAFT
                obj.started_at = None

    db.flush = AsyncMock(side_effect=flush)
    db.commit = AsyncMock()

    async def execute(statement):
        sql = str(statement).lower()
        result = MagicMock()
        if "from campaigns" in sql:
            result.scalar_one_or_none.return_value = next(
                (x for x in added if isinstance(x, Campaign)), None
            )
        elif "from agents" in sql:
            result.scalar_one_or_none.return_value = agent
        elif "from phone_numbers" in sql:
            result.scalar_one_or_none.return_value = phone if phone.is_active else None
        elif "from contacts" in sql:
            requested = next(v for v in statement.compile().params.values() if isinstance(v, list))
            result.scalars.return_value.all.return_value = [
                c for c in contacts if c.id in requested
            ]
        elif "from campaign_contacts" in sql:
            result.scalars.return_value.all.return_value = [
                x.contact_id for x in added if isinstance(x, CampaignContact)
            ]
        return result

    db.execute = AsyncMock(side_effect=execute)
    eligibility = RecipientEligibility(
        channel="sms",
        consent_required=True,
        checked_at=datetime.now(UTC),
        selected_count=2,
        eligible_count=2,
    )
    evaluate = AsyncMock(return_value=eligibility)
    # The real shared lifecycle still decides whether a draft can run.
    monkeypatch.setattr(fub_launch.RecipientEligibilityService, "evaluate_campaign", evaluate)
    monkeypatch.setattr(fub_launch.settings, "telnyx_api_key", "local-fixture-not-a-key")
    return db, ws, phone, added, eligibility


async def test_successful_launch_and_lost_response_retry_reuse_campaign(launch_fixture):
    db, ws, _, added, _ = launch_fixture
    first = await launch_fub_campaign(db, ws, [11, 12], "Selected campaign")
    second = await launch_fub_campaign(db, ws, [11, 12], "Selected campaign")
    assert first.launch_status == second.launch_status == "running"
    assert first.campaign_id == second.campaign_id == uuid.uuid5(ws, "onboarding-fub-launch")
    campaigns = [x for x in added if isinstance(x, Campaign)]
    recipients = [x for x in added if isinstance(x, CampaignContact)]
    assert len(campaigns) == 1
    assert campaigns[0].name == "Selected campaign"
    assert campaigns[0].status == CampaignStatus.RUNNING
    assert sorted(x.contact_id for x in recipients) == [11, 12]
    assert all(x.campaign_id == first.campaign_id for x in recipients)
    assert "FOR UPDATE" in str(db.execute.await_args_list[0].args[0])


async def test_missing_sender_blocks_without_creation_then_can_retry(launch_fixture):
    db, ws, phone, added, _ = launch_fixture
    phone.is_active = False
    result = await launch_fub_campaign(db, ws, [11, 12], "Lead Reactivation")
    assert result.launch_status == "blocked"
    assert result.campaign_id is None
    assert "SMS-enabled" in result.message
    assert not added
    phone.is_active = True
    result = await launch_fub_campaign(db, ws, [11, 12], "Lead Reactivation")
    assert result.launch_status == "running"


async def test_missing_consent_keeps_draft_id_and_retry_does_not_reenroll(launch_fixture):
    db, ws, _, added, eligibility = launch_fixture
    eligibility.eligible_count = 0
    first = await launch_fub_campaign(db, ws, [11, 12], "Lead Reactivation")
    assert first.launch_status == "blocked"
    assert first.campaign_status == "draft"
    assert first.campaign_id is not None
    eligibility.eligible_count = 2
    second = await launch_fub_campaign(db, ws, [11, 12], "Lead Reactivation")
    assert second.launch_status == "running"
    assert first.campaign_id == second.campaign_id
    assert len([x for x in added if isinstance(x, CampaignContact)]) == 2


async def test_corrected_partial_import_adds_only_new_contacts_to_blocked_draft(launch_fixture):
    db, ws, _, added, eligibility = launch_fixture
    eligibility.eligible_count = 0
    first = await launch_fub_campaign(db, ws, [11, 12], "Lead Reactivation")
    db.fixture_contacts.append(
        Contact(id=13, workspace_id=ws, first_name="Corrected", phone_number="+15555550113")
    )
    second = await launch_fub_campaign(db, ws, [11, 12, 13], "Lead Reactivation")
    assert second.launch_status == "blocked"
    assert second.campaign_id == first.campaign_id
    recipients = [x for x in added if isinstance(x, CampaignContact)]
    assert sorted(x.contact_id for x in recipients) == [11, 12, 13]
    eligibility.eligible_count = 3
    third = await launch_fub_campaign(db, ws, [11, 12, 13], "Lead Reactivation")
    assert third.launch_status == "running"
    assert len([x for x in added if isinstance(x, CampaignContact)]) == 3


async def test_large_import_uses_bounded_workspace_contact_queries(launch_fixture):
    db, ws, _, added, _ = launch_fixture
    db.fixture_contacts.extend(
        Contact(id=i, workspace_id=ws, first_name="Fixture", phone_number="+15555550100")
        for i in range(13, 1013)
    )
    ids = [contact.id for contact in db.fixture_contacts]
    result = await launch_fub_campaign(db, ws, ids, "Lead Reactivation")
    assert result.launch_status == "running"
    assert len([x for x in added if isinstance(x, CampaignContact)]) == len(ids)
    queries = [
        call.args[0]
        for call in db.execute.await_args_list
        if "from contacts" in str(call.args[0]).lower()
    ]
    assert len(queries) == 2
    for query in queries:
        requested = next(v for v in query.compile().params.values() if isinstance(v, list))
        assert len(requested) <= 1000
        assert ws in query.compile().params.values()


async def test_outside_sending_window_reports_deferred_not_sent(launch_fixture):
    db, ws, _, _, eligibility = launch_fixture
    eligibility.deferral_reason = "outside_sending_window"
    result = await launch_fub_campaign(db, ws, [11, 12], "Lead Reactivation")
    assert result.launch_status == "deferred"
    assert result.campaign_status == "running"
    assert "deferred" in result.message
