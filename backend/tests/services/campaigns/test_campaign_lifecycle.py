"""Tests for shared campaign lifecycle transitions."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.campaign import Campaign, CampaignContact, CampaignContactStatus, CampaignStatus
from app.models.contact import Contact
from app.services.campaigns.campaign_lifecycle import (
    CampaignLifecycleError,
    CampaignNotSendableError,
    pause_campaign,
    resume_campaign,
    start_campaign,
    summarize_campaign,
)
from app.services.campaigns.recipient_eligibility import RecipientEligibilityService
from app.services.compliance.outbound_compliance import OutboundComplianceService
from tests.factories import (
    CampaignContactFactory,
    CampaignFactory,
    ContactFactory,
    PhoneNumberFactory,
)


def _make_campaign(status: CampaignStatus = CampaignStatus.DRAFT) -> MagicMock:
    campaign = MagicMock()
    campaign.id = uuid.uuid4()
    campaign.name = "Spring Promo"
    campaign.status = status
    campaign.campaign_type = "sms"
    campaign.total_contacts = 10
    campaign.messages_sent = 5
    campaign.messages_delivered = 4
    campaign.messages_failed = 1
    campaign.replies_received = 2
    campaign.contacts_qualified = 1
    campaign.contacts_opted_out = 1
    campaign.appointments_booked = 1
    campaign.appointments_completed = 0
    campaign.calls_attempted = 0
    campaign.calls_answered = 0
    campaign.sms_fallbacks_sent = 0
    campaign.guarantee_target = None
    campaign.guarantee_status = None
    campaign.started_at = None
    campaign.completed_at = None
    return campaign


@pytest.mark.asyncio
async def test_start_campaign_sets_running_status() -> None:
    campaign = _make_campaign(CampaignStatus.DRAFT)

    campaign.campaign_type = "voice"  # SMS eligibility is covered below

    result = await start_campaign(AsyncMock(), campaign, contact_count=3)

    assert result.status == CampaignStatus.RUNNING
    assert result.contact_count == 3
    assert result.eligibility is None
    assert campaign.status == CampaignStatus.RUNNING
    assert campaign.started_at is not None


@pytest.mark.asyncio
async def test_start_campaign_rejects_invalid_transition() -> None:
    campaign = _make_campaign(CampaignStatus.COMPLETED)

    with pytest.raises(CampaignLifecycleError, match="Cannot start"):
        await start_campaign(AsyncMock(), campaign, contact_count=3)


@pytest.mark.asyncio
async def test_start_campaign_rejects_no_contacts() -> None:
    campaign = _make_campaign(CampaignStatus.DRAFT)

    with pytest.raises(CampaignLifecycleError, match="no contacts"):
        await start_campaign(AsyncMock(), campaign, contact_count=0)


@pytest.mark.asyncio
async def test_pause_campaign_sets_paused_status() -> None:
    campaign = _make_campaign(CampaignStatus.RUNNING)

    result = await pause_campaign(campaign)

    assert result.status == CampaignStatus.PAUSED
    assert campaign.status == CampaignStatus.PAUSED


@pytest.mark.asyncio
async def test_pause_campaign_rejects_non_running_campaign() -> None:
    campaign = _make_campaign(CampaignStatus.DRAFT)

    with pytest.raises(CampaignLifecycleError, match="running"):
        await pause_campaign(campaign)


@pytest.mark.asyncio
async def test_resume_campaign_sets_running_status() -> None:
    campaign = _make_campaign(CampaignStatus.PAUSED)
    campaign.campaign_type = "voice"

    result = await resume_campaign(AsyncMock(), campaign, contact_count=2)

    assert result.status == CampaignStatus.RUNNING
    assert result.contact_count == 2
    assert campaign.status == CampaignStatus.RUNNING


@pytest.mark.asyncio
async def test_resume_campaign_rejects_no_contacts() -> None:
    campaign = _make_campaign(CampaignStatus.PAUSED)

    with pytest.raises(CampaignLifecycleError, match="no contacts"):
        await resume_campaign(AsyncMock(), campaign, contact_count=0)


def test_summarize_campaign_returns_rates() -> None:
    campaign = _make_campaign(CampaignStatus.RUNNING)

    summary = summarize_campaign(campaign)

    assert summary["id"] == str(campaign.id)
    assert summary["status"] == "running"
    assert summary["rates"] == {
        "reply_rate": 0.4,
        "delivery_rate": 0.8,
        "qualification_rate": 0.1,
    }


# ---------------------------------------------------------------------------
# SMS launch eligibility (RF-012): launch rechecks the authoritative
# compliance rules, never infers consent, and refuses when nobody is eligible.
# ---------------------------------------------------------------------------


class _Result:
    """One result object serving every query the eligibility path issues."""

    def __init__(self, sender: object, rows: list[object]) -> None:
        self._sender = sender
        self._rows = rows

    def scalar_one_or_none(self) -> object:  # campaign sender lookup
        return self._sender

    def scalars(self) -> "_Result":  # campaign contacts
        return self

    def all(self) -> list[object]:
        return self._rows

    def scalar(self) -> bool:  # duplicate-send check: no earlier send
        return False


def _sms_audience(
    consents: list[str | None],
    *,
    status: CampaignStatus = CampaignStatus.DRAFT,
) -> tuple[Campaign, list[CampaignContact], list[Contact]]:
    workspace_id = uuid.uuid4()
    campaign = CampaignFactory.build(
        workspace_id=workspace_id, status=status, guarantee_target=None
    )
    contacts: list[Contact] = []
    rows: list[CampaignContact] = []
    for index, consent in enumerate(consents):
        contact = ContactFactory.build(
            id=1000 + index,
            workspace_id=workspace_id,
            phone_number=f"+1555300{index:04d}",
            sms_consent_status=consent,
        )
        contacts.append(contact)
        rows.append(
            CampaignContactFactory.build(
                campaign=campaign,
                campaign_id=campaign.id,
                contact=contact,
                contact_id=contact.id,
                status=CampaignContactStatus.PENDING,
            )
        )
    return campaign, rows, contacts


def _db_and_service(
    campaign: Campaign,
    rows: list[CampaignContact],
    *,
    opted_out: frozenset[str] = frozenset(),
) -> tuple[MagicMock, RecipientEligibilityService]:
    sender = PhoneNumberFactory.build(
        workspace_id=campaign.workspace_id,
        phone_number=campaign.from_phone_number,
        imessage_enabled=False,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(sender, rows))
    opt_out_manager = MagicMock()
    opt_out_manager.opted_out_numbers = AsyncMock(return_value=opted_out)
    compliance = OutboundComplianceService(opt_out_manager=opt_out_manager)
    return db, RecipientEligibilityService(compliance)


@pytest.mark.asyncio
async def test_start_sms_campaign_refuses_when_all_consent_unknown() -> None:
    campaign, rows, _ = _sms_audience([None, "unknown", None])
    db, service = _db_and_service(campaign, rows)

    with pytest.raises(CampaignNotSendableError, match="Record SMS consent") as excinfo:
        await start_campaign(db, campaign, contact_count=3, eligibility_service=service)

    eligibility = excinfo.value.eligibility
    assert eligibility.selected_count == 3
    assert eligibility.eligible_count == 0
    assert [(e.reason, e.count) for e in eligibility.exclusions] == [("missing_sms_consent", 3)]
    assert eligibility.exclusions[0].recoverable_with_consent
    assert sorted(eligibility.exclusions[0].contact_ids) == [1000, 1001, 1002]
    # Not reported as delivering, nothing persisted, consent never inferred.
    assert campaign.status == CampaignStatus.DRAFT
    assert campaign.started_at is None
    assert all(row.status == CampaignContactStatus.PENDING for row in rows)
    assert all(row.contact.sms_consent_status != "opted_in" for row in rows)


@pytest.mark.asyncio
async def test_start_sms_campaign_refuses_with_zero_eligible_from_mixed_reasons() -> None:
    campaign, rows, contacts = _sms_audience(["opted_in", None])
    db, service = _db_and_service(
        campaign, rows, opted_out=frozenset({contacts[0].phone_number})
    )

    with pytest.raises(CampaignNotSendableError) as excinfo:
        await start_campaign(db, campaign, contact_count=2, eligibility_service=service)

    reasons = {e.reason: e.count for e in excinfo.value.eligibility.exclusions}
    assert reasons == {"global_opt_out": 1, "missing_sms_consent": 1}
    assert campaign.status == CampaignStatus.DRAFT
    assert campaign.contacts_opted_out == 0


@pytest.mark.asyncio
async def test_start_sms_campaign_mixed_eligibility_excludes_with_reasons() -> None:
    campaign, rows, contacts = _sms_audience(["opted_in", "opted_in", None, "opted_in"])
    db, service = _db_and_service(
        campaign, rows, opted_out=frozenset({contacts[3].phone_number})
    )

    result = await start_campaign(db, campaign, contact_count=4, eligibility_service=service)

    assert result.status == CampaignStatus.RUNNING
    assert campaign.status == CampaignStatus.RUNNING
    assert result.eligibility is not None
    assert result.eligibility.eligible_count == 2
    assert result.eligibility.excluded_count == 2
    assert "2 of 4 recipients eligible now" in result.message
    assert "no sms consent on file" in result.message
    assert [row.status for row in rows] == [
        CampaignContactStatus.PENDING,
        CampaignContactStatus.PENDING,
        CampaignContactStatus.EXCLUDED,
        CampaignContactStatus.OPTED_OUT,
    ]
    assert rows[2].suppressed_reason == "missing_sms_consent"
    assert rows[3].suppressed_reason == "global_opt_out"
    assert rows[3].opted_out is True
    assert campaign.contacts_opted_out == 1


@pytest.mark.asyncio
async def test_start_rechecks_eligibility_that_changed_after_preview() -> None:
    campaign, rows, contacts = _sms_audience(["opted_in", "opted_in"])
    db, service = _db_and_service(campaign, rows)

    preview = await service.evaluate_campaign(db, campaign)
    assert preview.eligible_count == 2

    # Between preview and launch: one contact opts out, the other's consent
    # is withdrawn. Launch must not trust the stale preview.
    service.compliance_service.opt_out_manager.opted_out_numbers = AsyncMock(
        return_value=frozenset({contacts[0].phone_number})
    )
    contacts[1].sms_consent_status = "unknown"

    with pytest.raises(CampaignNotSendableError):
        await start_campaign(db, campaign, contact_count=2, eligibility_service=service)
    assert campaign.status == CampaignStatus.DRAFT


@pytest.mark.asyncio
async def test_start_reports_quiet_hours_as_deferral_not_exclusion() -> None:
    campaign, rows, _ = _sms_audience(["opted_in"])
    campaign.quiet_hours_start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC).time()
    campaign.quiet_hours_end = datetime(2026, 1, 1, 23, 59, tzinfo=UTC).time()
    campaign.quiet_hours_timezone = "UTC"
    db, service = _db_and_service(campaign, rows)

    result = await start_campaign(db, campaign, contact_count=1, eligibility_service=service)

    assert result.eligibility is not None
    assert result.eligibility.eligible_count == 1
    assert result.eligibility.excluded_count == 0
    assert result.eligibility.deferral_reason == "quiet_hours"
    assert rows[0].status == CampaignContactStatus.PENDING


@pytest.mark.asyncio
async def test_resume_requeues_recipients_whose_consent_was_recorded() -> None:
    campaign, rows, contacts = _sms_audience([None, None], status=CampaignStatus.PAUSED)
    for row in rows:
        row.status = CampaignContactStatus.EXCLUDED
        row.suppressed_reason = "missing_sms_consent"
    contacts[0].sms_consent_status = "opted_in"  # operator recorded consent
    db, service = _db_and_service(campaign, rows)

    result = await resume_campaign(db, campaign, contact_count=2, eligibility_service=service)

    assert result.status == CampaignStatus.RUNNING
    assert rows[0].status == CampaignContactStatus.PENDING
    assert rows[0].suppressed_reason is None
    assert rows[1].status == CampaignContactStatus.EXCLUDED
    assert rows[1].suppressed_reason == "missing_sms_consent"
