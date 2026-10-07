"""Pre-launch SMS recipient eligibility preview (RF-012)."""

import uuid
from datetime import UTC, datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.contact import Contact
from app.services.campaigns.recipient_eligibility import (
    RecipientEligibilityService,
    build_draft_campaign,
)
from app.services.compliance.outbound_compliance import OutboundComplianceService
from tests.factories import ContactFactory, PhoneNumberFactory


class _Result:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> "_Result":
        return self

    def all(self) -> list[object]:
        return self._rows


def _service(opted_out: frozenset[str] = frozenset()) -> RecipientEligibilityService:
    manager = MagicMock()
    manager.opted_out_numbers = AsyncMock(return_value=opted_out)
    return RecipientEligibilityService(OutboundComplianceService(opt_out_manager=manager))


def _contacts(workspace_id: uuid.UUID, consents: list[str | None]) -> list[Contact]:
    return [
        ContactFactory.build(
            id=10 + index,
            workspace_id=workspace_id,
            phone_number=f"+1555400{index:04d}",
            sms_consent_status=consent,
        )
        for index, consent in enumerate(consents)
    ]


@pytest.mark.asyncio
async def test_preview_reports_selected_eligible_and_exclusion_reasons() -> None:
    workspace_id = uuid.uuid4()
    contacts = _contacts(workspace_id, ["opted_in", None, "unknown", "opted_in"])
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(contacts))
    draft = build_draft_campaign(
        workspace_id=workspace_id,
        from_phone_number="+15550001111",
        sending_hours_start=None,
        sending_hours_end=None,
        sending_days=None,
        timezone="America/New_York",
    )
    sender = PhoneNumberFactory.build(workspace_id=workspace_id, imessage_enabled=False)

    # Contact 99 is selected but not in this workspace's rows (workspace scoping).
    summary = await _service(frozenset({contacts[3].phone_number})).preview_contacts(
        db, campaign=draft, contact_ids=[10, 11, 12, 13, 99, 10], sender=sender
    )

    assert summary.consent_required is True
    assert summary.selected_count == 5  # de-duplicated selection
    assert summary.eligible_count == 1
    assert summary.ready_to_send is True
    assert {e.reason: e.count for e in summary.exclusions} == {
        "missing_sms_consent": 2,
        "global_opt_out": 1,
        "contact_not_found": 1,
    }
    consent = next(e for e in summary.exclusions if e.reason == "missing_sms_consent")
    assert consent.recoverable_with_consent and sorted(consent.contact_ids) == [11, 12]
    # Preview is read-only: consent is never inferred.
    assert contacts[1].sms_consent_status is None


@pytest.mark.asyncio
async def test_preview_all_unknown_consent_is_not_ready() -> None:
    workspace_id = uuid.uuid4()
    contacts = _contacts(workspace_id, [None, None])
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(contacts))
    draft = build_draft_campaign(
        workspace_id=workspace_id,
        from_phone_number="+15550001111",
        sending_hours_start=None,
        sending_hours_end=None,
        sending_days=None,
        timezone="UTC",
    )

    summary = await _service().preview_contacts(
        db, campaign=draft, contact_ids=[10, 11], sender=None
    )

    assert summary.eligible_count == 0
    assert summary.ready_to_send is False
    assert summary.exclusion_summary() == "2 no sms consent on file"


@pytest.mark.asyncio
async def test_preview_imessage_sender_does_not_require_sms_consent() -> None:
    workspace_id = uuid.uuid4()
    contacts = _contacts(workspace_id, [None])
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(contacts))
    draft = build_draft_campaign(
        workspace_id=workspace_id,
        from_phone_number="+15550001111",
        sending_hours_start=None,
        sending_hours_end=None,
        sending_days=None,
        timezone="UTC",
    )
    sender = PhoneNumberFactory.build(workspace_id=workspace_id, imessage_enabled=True)

    summary = await _service().preview_contacts(
        db, campaign=draft, contact_ids=[10], sender=sender
    )

    assert summary.channel == "imessage"
    assert summary.eligible_count == 1


@pytest.mark.asyncio
async def test_preview_flags_closed_sending_window_as_deferral() -> None:
    workspace_id = uuid.uuid4()
    contacts = _contacts(workspace_id, ["opted_in"])
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(contacts))
    draft = build_draft_campaign(
        workspace_id=workspace_id,
        from_phone_number="+15550001111",
        sending_hours_start=time(9, 0),
        sending_hours_end=time(17, 0),
        sending_days=None,
        timezone="UTC",
    )

    summary = await _service().preview_contacts(
        db,
        campaign=draft,
        contact_ids=[10],
        sender=None,
        now=datetime(2026, 10, 7, 20, 0, tzinfo=UTC),  # after 17:00
    )

    assert summary.eligible_count == 1
    assert summary.excluded_count == 0
    assert summary.deferral_reason == "outside_sending_window"
