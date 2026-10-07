"""Operator-attested SMS consent recording (RF-012 recovery path)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.schemas.contact import SmsConsentRecordRequest
from app.services.compliance.sms_consent import SmsConsentValidationError, record_sms_consent
from tests.factories import ContactFactory


class _Result:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> "_Result":
        return self

    def all(self) -> list[object]:
        return self._rows


@pytest.mark.asyncio
async def test_records_consent_but_never_overrides_opt_out() -> None:
    workspace_id = uuid.uuid4()
    unknown = ContactFactory.build(id=1, workspace_id=workspace_id, sms_consent_status=None)
    opted_out = ContactFactory.build(
        id=2, workspace_id=workspace_id, sms_consent_status=None, phone_number="+15550009999"
    )
    already = ContactFactory.build(id=3, workspace_id=workspace_id, sms_consent_status="opted_in")
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result([unknown, opted_out, already]))
    manager = MagicMock()
    manager.opted_out_numbers = AsyncMock(return_value=frozenset({"+15550009999"}))

    result = await record_sms_consent(
        db,
        workspace_id=workspace_id,
        contact_ids=[1, 2, 3, 404],
        source="web_form",
        collected_at=None,
        notes="Open house sign-in sheet",
        recorded_by_user_id=7,
        opt_out_manager=manager,
    )

    assert result.updated == 1
    assert result.already_opted_in == 1
    assert result.skipped_opted_out == [2]
    assert result.not_found == [404]
    assert unknown.sms_consent_status == "opted_in"
    assert unknown.sms_consent_source == "web_form"
    assert unknown.sms_consent_collected_at is not None
    assert "user 7" in (unknown.sms_consent_notes or "")
    assert opted_out.sms_consent_status is None


@pytest.mark.asyncio
async def test_rejects_future_collection_date() -> None:
    with pytest.raises(SmsConsentValidationError, match="future"):
        await record_sms_consent(
            MagicMock(),
            workspace_id=uuid.uuid4(),
            contact_ids=[1],
            source="paper_form",
            collected_at=datetime.now(UTC) + timedelta(days=1),
            notes=None,
            recorded_by_user_id=1,
        )


def test_request_requires_explicit_attestation_and_known_source() -> None:
    with pytest.raises(ValidationError):
        SmsConsentRecordRequest.model_validate({"ids": [1], "source": "web_form"})
    with pytest.raises(ValidationError):
        SmsConsentRecordRequest.model_validate(
            {"ids": [1], "source": "web_form", "attested": False}
        )
    with pytest.raises(ValidationError):
        SmsConsentRecordRequest.model_validate(
            {"ids": [1], "source": "imported", "attested": True}
        )
    assert SmsConsentRecordRequest.model_validate(
        {"ids": [1], "source": "web_form", "attested": True}
    ).attested
