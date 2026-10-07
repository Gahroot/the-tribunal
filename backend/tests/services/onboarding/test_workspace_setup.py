"""Unit tests for realtor onboarding workspace setup workflows."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.agent import Agent
from app.models.campaign import Campaign, CampaignContact, CampaignStatus
from app.models.contact import Contact
from app.models.phone_number import PhoneNumber
from app.models.workspace import Workspace, WorkspaceMembership
from app.services.contacts import ImportResult
from app.services.onboarding.exceptions import OnboardingValidationError, OnboardingWorkspaceError
from app.services.onboarding.workspace_setup import (
    REALTOR_AGENT_NAME,
    RealtorCampaignInput,
    RealtorOnboardingInput,
    complete_realtor_onboarding,
    get_user_workspace,
    launch_realtor_campaign_from_csv,
    provision_realtor_phone_number,
)
from app.services.telephony.telnyx import PhoneNumberInfo


class _ExecuteResult:
    def __init__(self, row: Any | None = None, scalar: int | None = None) -> None:
        self._row = row
        self._scalar = scalar

    def scalar_one_or_none(self) -> Any | None:
        return self._row

    def scalar(self) -> int | None:
        return self._scalar


@dataclass(slots=True)
class _MockTelnyxService:
    available_numbers: list[PhoneNumberInfo]
    purchased_number: PhoneNumberInfo | None = None
    raises_on_purchase: bool = False
    search_calls: list[dict[str, Any]] | None = None
    purchase_calls: list[str] | None = None
    closed: bool = False

    def __post_init__(self) -> None:
        self.search_calls = []
        self.purchase_calls = []

    async def search_phone_numbers(
        self,
        *,
        country: str,
        area_code: str | None,
        limit: int,
    ) -> list[PhoneNumberInfo]:
        self.search_calls.append({"country": country, "area_code": area_code, "limit": limit})
        return self.available_numbers

    async def purchase_phone_number(self, phone_number: str) -> PhoneNumberInfo:
        self.purchase_calls.append(phone_number)
        if self.raises_on_purchase:
            raise RuntimeError("telnyx down")
        if self.purchased_number is None:
            raise AssertionError("purchased_number must be configured")
        return self.purchased_number

    async def close(self) -> None:
        self.closed = True


def _db() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock(side_effect=lambda: _assign_ids(session.add.call_args_list))
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _assign_ids(add_calls: list[Any]) -> None:
    for call in add_calls:
        obj = call.args[0]
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            if isinstance(obj, Contact):
                obj.id = 101
            else:
                obj.id = uuid.uuid4()


def _workspace(user_id: int = 7) -> tuple[WorkspaceMembership, Workspace]:
    workspace_id = uuid.uuid4()
    membership = WorkspaceMembership(
        id=uuid.uuid4(),
        user_id=user_id,
        workspace_id=workspace_id,
        is_default=True,
        role="owner",
    )
    workspace = Workspace(
        id=workspace_id,
        name="Jane Realty",
        slug="jane-realty",
        is_active=True,
    )
    return membership, workspace


def _contact(workspace_id: uuid.UUID, contact_id: int) -> Contact:
    return Contact(
        id=contact_id,
        workspace_id=workspace_id,
        first_name=f"Lead {contact_id}",
        phone_number=f"+1555000{contact_id:04d}",
        phone_hash=f"phone-{contact_id}",
        status="new",
    )


def _agent(workspace_id: uuid.UUID) -> Agent:
    return Agent(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name=REALTOR_AGENT_NAME,
        channel_mode="text",
        voice_provider="openai",
        voice_id="alloy",
        language="en-US",
        system_prompt="Be helpful.",
        temperature=0.7,
        max_tokens=500,
        text_response_delay_ms=30_000,
        text_max_context_messages=20,
        enabled_tools=["book_appointment"],
        tool_settings={},
    )


def _phone(workspace_id: uuid.UUID) -> PhoneNumber:
    return PhoneNumber(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        phone_number="+15555550100",
        sms_enabled=True,
        voice_enabled=True,
        is_active=True,
    )


async def test_get_user_workspace_uses_default_membership() -> None:
    db = _db()
    membership, workspace = _workspace(user_id=7)
    db.execute.side_effect = [_ExecuteResult(membership), _ExecuteResult(workspace)]

    result = await get_user_workspace(7, db)

    assert result is workspace
    assert db.execute.await_count == 2


async def test_get_user_workspace_raises_when_user_has_no_membership() -> None:
    db = _db()
    db.execute.side_effect = [_ExecuteResult(None), _ExecuteResult(None)]

    with pytest.raises(OnboardingWorkspaceError) as exc_info:
        await get_user_workspace(7, db)

    assert exc_info.value.message == "No workspace found. Please create a workspace first."


async def test_complete_realtor_onboarding_stores_credentials_and_purchases_phone() -> None:
    db = _db()
    membership, workspace = _workspace(user_id=7)
    db.execute.side_effect = [
        _ExecuteResult(membership),
        _ExecuteResult(workspace),
        _ExecuteResult(None),  # no existing realtor agent
        _ExecuteResult(None),  # no Cal.com integration yet
        _ExecuteResult(None),  # no FUB integration yet
        _ExecuteResult(None),  # no existing SMS number
    ]
    available_number = PhoneNumberInfo(id="", phone_number="+15555550123")
    purchased_number = PhoneNumberInfo(id="telnyx-123", phone_number="+15555550123")
    telnyx = _MockTelnyxService([available_number], purchased_number)

    result = await complete_realtor_onboarding(
        db=db,
        current_user_id=7,
        request=RealtorOnboardingInput(
            calcom_api_key="cal_key",
            calcom_event_type_id=123,
            area_code="512",
            fub_api_key="fub_key",
        ),
        telnyx_api_key="telnyx_key",
        telnyx_service_factory=lambda api_key: telnyx,
    )

    assert result.workspace_id == workspace.id
    assert result.agent_id is not None
    assert result.phone_number_id is not None
    assert result.phone_number == "+15555550123"
    assert result.calcom_connected is True
    assert telnyx.search_calls == [{"country": "US", "area_code": "512", "limit": 5}]
    assert telnyx.purchase_calls == ["+15555550123"]
    assert telnyx.closed is True
    assert db.add.call_count == 4
    added_types = [type(call.args[0]) for call in db.add.call_args_list]
    assert Agent in added_types
    assert PhoneNumber in added_types
    db.commit.assert_awaited_once()


async def test_provision_realtor_phone_number_is_best_effort_on_telnyx_error() -> None:
    db = _db()
    db.execute.side_effect = [_ExecuteResult(None)]
    workspace_id = uuid.uuid4()
    available_number = PhoneNumberInfo(id="", phone_number="+15555550123")
    telnyx = _MockTelnyxService([available_number], raises_on_purchase=True)

    result = await provision_realtor_phone_number(
        db=db,
        workspace_id=workspace_id,
        area_code="512",
        telnyx_api_key="telnyx_key",
        telnyx_service_factory=lambda api_key: telnyx,
    )

    assert result.phone_number_id is None
    assert result.phone_number is None
    assert telnyx.closed is True
    assert db.add.call_count == 0


async def test_launch_realtor_campaign_imports_contacts_and_starts_campaign() -> None:
    db = _db()
    membership, workspace = _workspace(user_id=7)
    agent = _agent(workspace.id)
    phone = _phone(workspace.id)
    contacts = [_contact(workspace.id, 101), _contact(workspace.id, 102)]
    db.execute.side_effect = [
        _ExecuteResult(membership),
        _ExecuteResult(workspace),
        _ExecuteResult(agent),
        _ExecuteResult(phone),
    ]
    import_result = ImportResult(
        total_rows=2,
        successful=2,
        failed=0,
        skipped_duplicates=1,
        created_contacts=contacts,
    )
    import_service = MagicMock()
    import_service.import_csv = AsyncMock(return_value=import_result)
    drip_bootstrapper = AsyncMock()

    def now() -> datetime:
        return datetime(2026, 6, 1, 14, 30, tzinfo=UTC)

    result = await launch_realtor_campaign_from_csv(
        db=db,
        current_user_id=7,
        request=RealtorCampaignInput(
            file_content=b"first_name,phone_number\nAva,+15550000001\n",
            skip_duplicates=True,
            campaign_name=None,
        ),
        import_service_factory=lambda session: import_service,
        drip_bootstrapper=drip_bootstrapper,
        now=now,
    )

    import_service.import_csv.assert_awaited_once_with(
        workspace_id=workspace.id,
        file_content=b"first_name,phone_number\nAva,+15550000001\n",
        skip_duplicates=True,
        source="realtor_csv_upload",
    )
    drip_bootstrapper.assert_awaited_once_with(db, workspace.id, [101, 102])
    assert result.campaign_name == "Lead Reactivation - June 01, 2026"
    assert result.campaign_status == CampaignStatus.RUNNING
    assert result.contacts_imported == 2
    assert result.contacts_skipped == 1
    assert result.contacts_failed == 0
    assert result.phone_number_used == phone.phone_number
    assert result.agent_id == agent.id
    assert result.started_at == datetime(2026, 6, 1, 14, 30, tzinfo=UTC)
    assert result.workspace_id == workspace.id
    campaigns = [
        call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], Campaign)
    ]
    assert len(campaigns) == 1
    assert campaigns[0].total_contacts == 2
    campaign_contacts = [
        call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], CampaignContact)
    ]
    assert [row.contact_id for row in campaign_contacts] == [101, 102]
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(campaigns[0])


async def test_launch_realtor_campaign_rejects_empty_import() -> None:
    db = _db()
    membership, workspace = _workspace(user_id=7)
    db.execute.side_effect = [
        _ExecuteResult(membership),
        _ExecuteResult(workspace),
        _ExecuteResult(_agent(workspace.id)),
        _ExecuteResult(_phone(workspace.id)),
    ]
    import_result = ImportResult(
        total_rows=3,
        successful=0,
        failed=1,
        skipped_duplicates=2,
        created_contacts=[],
    )
    import_service = MagicMock()
    import_service.import_csv = AsyncMock(return_value=import_result)

    with pytest.raises(OnboardingValidationError) as exc_info:
        await launch_realtor_campaign_from_csv(
            db=db,
            current_user_id=7,
            request=RealtorCampaignInput(
                file_content=b"first_name,phone_number\n",
                skip_duplicates=True,
            ),
            import_service_factory=lambda session: import_service,
            drip_bootstrapper=AsyncMock(),
        )

    assert "No contacts were imported from the CSV" in exc_info.value.message
    db.commit.assert_not_awaited()


# --- Explicit workspace handoff (RF-005) -----------------------------------


def _compiled(statement: Any) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": True})).lower()


async def test_onboarding_explicit_workspace_never_resolves_default() -> None:
    """A second, selected workspace gets the agent, credentials, and phone."""
    db = _db()
    default_membership, default_workspace = _workspace(user_id=7)
    selected_id = uuid.uuid4()
    assert selected_id != default_workspace.id
    db.execute.side_effect = [
        _ExecuteResult(None),  # realtor agent lookup
        _ExecuteResult(None),  # Cal.com integration lookup
        _ExecuteResult(None),  # FUB integration lookup
        _ExecuteResult(None),  # existing SMS number lookup
    ]
    purchased = PhoneNumberInfo(id="telnyx-9", phone_number="+15555550999")
    telnyx = _MockTelnyxService([purchased], purchased)

    result = await complete_realtor_onboarding(
        db=db,
        current_user_id=7,
        workspace_id=selected_id,
        request=RealtorOnboardingInput(
            calcom_api_key="cal_key",
            calcom_event_type_id=55,
            fub_api_key="fub_key",
        ),
        telnyx_api_key="test-key",
        telnyx_service_factory=lambda api_key: telnyx,
    )

    assert result.workspace_id == selected_id
    statements = [_compiled(call.args[0]) for call in db.execute.await_args_list]
    assert not any("workspace_memberships" in sql for sql in statements)
    assert all(selected_id.hex in sql for sql in statements)
    added = [call.args[0] for call in db.add.call_args_list]
    assert {obj.workspace_id for obj in added} == {selected_id}
    assert {type(obj) for obj in added} >= {Agent, PhoneNumber}


async def test_onboarding_retry_reuses_agent_and_phone_without_purchase() -> None:
    """Retrying after a partial setup must not duplicate the agent or buy a number."""
    db = _db()
    selected_id = uuid.uuid4()
    agent = _agent(selected_id)
    agent.calcom_event_type_id = 1
    phone = _phone(selected_id)
    db.execute.side_effect = [
        _ExecuteResult(agent),  # existing realtor agent
        _ExecuteResult(None),  # Cal.com integration (upsert creates)
        _ExecuteResult(phone),  # existing SMS number
    ]
    telnyx = _MockTelnyxService([], None)

    result = await complete_realtor_onboarding(
        db=db,
        current_user_id=7,
        workspace_id=selected_id,
        request=RealtorOnboardingInput(calcom_api_key="cal_key", calcom_event_type_id=42),
        telnyx_api_key="test-key",
        telnyx_service_factory=lambda api_key: telnyx,
    )

    assert result.agent_id == agent.id
    assert result.phone_number_id == phone.id
    assert result.phone_number == phone.phone_number
    assert agent.calcom_event_type_id == 42
    assert telnyx.search_calls == []
    assert telnyx.purchase_calls == []
    added_types = [type(call.args[0]) for call in db.add.call_args_list]
    assert Agent not in added_types
    assert PhoneNumber not in added_types
    db.commit.assert_awaited_once()


async def test_campaign_launch_targets_selected_workspace_not_default() -> None:
    db = _db()
    selected_id = uuid.uuid4()
    agent = _agent(selected_id)
    phone = _phone(selected_id)
    db.execute.side_effect = [_ExecuteResult(agent), _ExecuteResult(phone)]
    import_service = MagicMock()
    import_service.import_csv = AsyncMock(
        return_value=ImportResult(
            total_rows=1,
            successful=1,
            failed=0,
            skipped_duplicates=0,
            created_contacts=[_contact(selected_id, 101)],
        )
    )
    drip_bootstrapper = AsyncMock()

    result = await launch_realtor_campaign_from_csv(
        db=db,
        current_user_id=7,
        workspace_id=selected_id,
        request=RealtorCampaignInput(file_content=b"csv", skip_duplicates=True),
        import_service_factory=lambda session: import_service,
        drip_bootstrapper=drip_bootstrapper,
    )

    assert result.workspace_id == selected_id
    assert import_service.import_csv.await_args.kwargs["workspace_id"] == selected_id
    drip_bootstrapper.assert_awaited_once_with(db, selected_id, [101])
    statements = [_compiled(call.args[0]) for call in db.execute.await_args_list]
    assert not any("workspace_memberships" in sql for sql in statements)
    campaigns = [
        call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], Campaign)
    ]
    assert [c.workspace_id for c in campaigns] == [selected_id]


async def test_campaign_launch_without_phone_fails_before_importing_contacts() -> None:
    """No SMS number must fail before contacts commit so a retry still launches."""
    db = _db()
    selected_id = uuid.uuid4()
    db.execute.side_effect = [_ExecuteResult(_agent(selected_id)), _ExecuteResult(None)]
    import_service = MagicMock()
    import_service.import_csv = AsyncMock()

    with pytest.raises(OnboardingValidationError) as exc_info:
        await launch_realtor_campaign_from_csv(
            db=db,
            current_user_id=7,
            workspace_id=selected_id,
            request=RealtorCampaignInput(file_content=b"csv", skip_duplicates=True),
            import_service_factory=lambda session: import_service,
            drip_bootstrapper=AsyncMock(),
        )

    assert "SMS-enabled phone number" in exc_info.value.message
    import_service.import_csv.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_legacy_default_resolution_tolerates_multiple_default_memberships() -> None:
    """Legacy callers must not 500 when several memberships are flagged default."""
    db = _db()
    membership, workspace = _workspace(user_id=7)
    db.execute.side_effect = [_ExecuteResult(membership), _ExecuteResult(workspace)]

    resolved = await get_user_workspace(7, db)

    assert resolved is workspace
    default_query = _compiled(db.execute.await_args_list[0].args[0])
    assert "order by workspace_memberships.created_at asc" in default_query
    assert "limit 1" in default_query
