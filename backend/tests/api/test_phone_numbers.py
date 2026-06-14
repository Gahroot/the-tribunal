"""Phone number API behavior."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.api.v1 import phone_numbers
from app.schemas.phone_number import PurchasePhoneNumberRequest, SearchPhoneNumbersRequest
from app.services.telephony import availability


class _NoIntegrationResult:
    def scalar_one_or_none(self) -> None:
        return None


def _db_without_telnyx_integration() -> AsyncMock:
    db = AsyncMock()
    db.execute.return_value = _NoIntegrationResult()
    return db


async def test_search_phone_numbers_returns_actionable_424_when_telephony_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(availability.settings, "telnyx_api_key", "")
    telnyx_service = MagicMock()
    monkeypatch.setattr(phone_numbers, "TelnyxSMSService", telnyx_service)

    with pytest.raises(HTTPException) as exc_info:
        await phone_numbers.search_phone_numbers(
            workspace_id=uuid.uuid4(),
            request_data=SearchPhoneNumbersRequest(country="US", limit=1),
            current_user=MagicMock(),
            db=_db_without_telnyx_integration(),
            workspace=MagicMock(),
        )

    assert exc_info.value.status_code == status.HTTP_424_FAILED_DEPENDENCY
    assert exc_info.value.detail == availability.telephony_unavailable_detail()
    telnyx_service.assert_not_called()


async def test_purchase_phone_number_returns_actionable_424_when_telephony_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(availability.settings, "telnyx_api_key", "")
    telnyx_service = MagicMock()
    monkeypatch.setattr(phone_numbers, "TelnyxSMSService", telnyx_service)

    with pytest.raises(HTTPException) as exc_info:
        await phone_numbers.purchase_phone_number(
            workspace_id=uuid.uuid4(),
            request_data=PurchasePhoneNumberRequest(phone_number="+15551234567"),
            current_user=MagicMock(),
            db=_db_without_telnyx_integration(),
            workspace=MagicMock(),
        )

    assert exc_info.value.status_code == status.HTTP_424_FAILED_DEPENDENCY
    assert exc_info.value.detail == availability.telephony_unavailable_detail()
    telnyx_service.assert_not_called()


async def test_telephony_status_reports_unavailable_with_settings_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(availability.settings, "telnyx_api_key", "")

    response = await phone_numbers.get_phone_number_telephony_status(
        workspace_id=uuid.uuid4(),
        current_user=MagicMock(),
        db=_db_without_telnyx_integration(),
        workspace=MagicMock(),
    )

    assert response.enabled is False
    assert response.provider == "telnyx"
    assert response.action_href == availability.TELEPHONY_SETUP_ACTION_HREF
    assert "connect Telnyx" in response.message


async def test_telephony_status_reports_available_for_server_telnyx_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(availability.settings, "telnyx_api_key", "server-key")
    db = _db_without_telnyx_integration()

    response = await phone_numbers.get_phone_number_telephony_status(
        workspace_id=uuid.uuid4(),
        current_user=MagicMock(),
        db=db,
        workspace=MagicMock(),
    )

    assert response.enabled is True
    assert response.action_href is None
    db.execute.assert_not_called()
