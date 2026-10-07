"""RF-011: AI booking uses the active workspace's encrypted Cal.com connection.

Real service paths (credential resolver, text/voice tool executors, voice
session factory, approval handler) run end to end. Only two boundaries are
stubbed:

* the database — an in-memory fake that honours the compiled ``workspace_id`` /
  ``integration_type`` predicates, so cross-workspace leaks would surface;
* the Cal.com HTTP API — ``httpx.MockTransport`` behind the real
  ``AsyncProviderHTTPClient``, recording which API key each request carried.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

import app.db.session as db_session_module
from app.core.config import settings
from app.core.encryption import encrypt_json
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.pending_action import PendingAction
from app.models.workspace import WorkspaceIntegration
from app.services.ai.text_response_generator import text_booking_enabled
from app.services.ai.text_tool_executor import TextToolExecutor
from app.services.ai.tool_executor import VoiceToolExecutor
from app.services.ai.voice_session_factory import VoiceSessionFactory
from app.services.approval.approval_gate_service import BookAppointmentActionHandler
from app.services.calendar.calcom_credentials import (
    CALCOM_API_KEY_MISSING,
    CALCOM_AUTH_FAILED,
    CALCOM_CREDENTIALS_UNREADABLE,
    CALCOM_EVENT_TYPE_MISSING,
    CALCOM_INTEGRATION_INACTIVE,
    CALCOM_NOT_CONNECTED,
    CALCOM_PROVIDER_ERROR,
    CalComCredentialError,
    resolve_calcom_credentials,
)
from app.services.providers.http import AsyncProviderHTTPClient

WS_A = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
WS_B = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
WS_NONE = uuid.UUID("cccccccc-0000-4000-8000-000000000003")
KEY_A = "cal_live_workspace_a"
KEY_B = "cal_live_workspace_b"
GLOBAL_KEY = "cal_live_global_env"
SLOT_DAY = (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%d")
SLOT_ISO = f"{SLOT_DAY}T19:00:00.000Z"
CONTACT_ID = 301


# ── Boundaries ───────────────────────────────────────────────────────────────


class _Result:
    def __init__(self, row: Any | None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any | None:
        return self._row

    def scalars(self) -> _Result:
        return self

    def first(self) -> Any | None:
        return self._row


class _ScopedDB:
    """Fake AsyncSession that filters rows by the query's compiled predicates."""

    def __init__(self, integrations: list[WorkspaceIntegration], agents: list[Any] = ()) -> None:
        self.integrations = list(integrations)
        self.agents = list(agents)
        self.contacts = [
            Contact(id=CONTACT_ID, workspace_id=ws, first_name="Lead", email="lead@example.test")
            for ws in (WS_A, WS_B)
        ]
        self.added: list[Any] = []
        self.queries: list[dict[str, Any]] = []

    async def __aenter__(self) -> _ScopedDB:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None

    async def execute(self, query: Any) -> _Result:
        params = query.compile().params
        self.queries.append(params)
        entity = query.column_descriptions[0]["entity"]
        if entity is WorkspaceIntegration:
            row = next(
                (
                    i
                    for i in self.integrations
                    if i.workspace_id == params["workspace_id_1"]
                    and i.integration_type == params["integration_type_1"]
                ),
                None,
            )
            return _Result(row)
        if entity is Agent:
            row = next(
                (
                    a
                    for a in self.agents
                    if a.id == params["id_1"] and a.workspace_id == params["workspace_id_1"]
                ),
                None,
            )
            return _Result(row)
        if entity is Contact:
            row = next(
                (
                    c
                    for c in self.contacts
                    if c.id == params["id_1"] and c.workspace_id == params["workspace_id_1"]
                ),
                None,
            )
            return _Result(row)
        if entity is Appointment:
            return _Result(None)
        raise AssertionError(f"unexpected query on {entity}")

    def add(self, row: Any) -> None:
        self.added.append(row)

    def begin_nested(self) -> _ScopedDB:
        return self

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


def _integration(
    workspace_id: uuid.UUID,
    credentials: dict[str, Any] | None = None,
    *,
    is_active: bool = True,
    encrypted: str | None = None,
) -> WorkspaceIntegration:
    return WorkspaceIntegration(
        workspace_id=workspace_id,
        integration_type="calcom",
        encrypted_credentials=encrypted or encrypt_json(credentials or {}),
        is_active=is_active,
    )


@pytest.fixture
def calcom_wire(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub the Cal.com HTTP boundary; record the bearer key on each request."""
    state: dict[str, Any] = {"requests": [], "rejected_keys": set()}

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers.get("Authorization", "").removeprefix("Bearer ")
        state["requests"].append((request.method, request.url.path, key))
        state.setdefault("params", []).append(dict(request.url.params))
        if key in state["rejected_keys"]:
            return httpx.Response(401, json={"message": "Invalid API key"})
        if request.method == "GET" and request.url.path == "/v2/slots/available":
            return httpx.Response(
                200, json={"status": "success", "data": {"slots": {SLOT_DAY: [{"time": SLOT_ISO}]}}}
            )
        if request.method == "POST" and request.url.path == "/v2/bookings":
            return httpx.Response(
                201, json={"status": "success", "data": {"uid": f"uid-{key}", "id": 42}}
            )
        return httpx.Response(404, json={"message": "not found"})

    class WireClient(AsyncProviderHTTPClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("app.services.calendar.calcom.AsyncProviderHTTPClient", WireClient)
    return state


@pytest.fixture(autouse=True)
def _no_global_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "calcom_api_key", "", raising=False)


def _agent(workspace_id: uuid.UUID, **overrides: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "workspace_id": workspace_id,
        "calcom_event_type_id": 777,
        "assignment_strategy": "single",
        "enabled_tools": ["book_appointment"],
        "tool_settings": {},
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _text_executor(db: _ScopedDB, workspace_id: uuid.UUID) -> TextToolExecutor:
    conversation = SimpleNamespace(id=uuid.uuid4(), workspace_id=workspace_id, contact_id=None)
    return TextToolExecutor(
        agent=_agent(workspace_id),  # type: ignore[arg-type]
        conversation=conversation,  # type: ignore[arg-type]
        db=db,  # type: ignore[arg-type]
        timezone="America/Denver",
    )


# ── Resolver ─────────────────────────────────────────────────────────────────


async def test_saved_workspace_key_resolves_without_global_key() -> None:
    db = _ScopedDB([_integration(WS_A, {"api_key": KEY_A})])

    creds = await resolve_calcom_credentials(db, WS_A)  # type: ignore[arg-type]

    assert creds.api_key == KEY_A
    assert creds.source == "workspace"
    assert KEY_A not in repr(creds)


async def test_distinct_workspaces_never_share_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "calcom_api_key", GLOBAL_KEY, raising=False)
    db = _ScopedDB([_integration(WS_A, {"api_key": KEY_A}), _integration(WS_B, {"api_key": KEY_B})])

    assert (await resolve_calcom_credentials(db, WS_A)).api_key == KEY_A  # type: ignore[arg-type]
    assert (await resolve_calcom_credentials(db, WS_B)).api_key == KEY_B  # type: ignore[arg-type]
    # Documented fallback only for a workspace that never connected Cal.com.
    fallback = await resolve_calcom_credentials(db, WS_NONE)  # type: ignore[arg-type]
    assert (fallback.api_key, fallback.source) == (GLOBAL_KEY, "global")


@pytest.mark.parametrize(
    ("integration", "code"),
    [
        (None, CALCOM_NOT_CONNECTED),
        (_integration(WS_A, {"api_key": KEY_A}, is_active=False), CALCOM_INTEGRATION_INACTIVE),
        (_integration(WS_A, encrypted="not-a-fernet-token"), CALCOM_CREDENTIALS_UNREADABLE),
        (_integration(WS_A, {"api_key": "  "}), CALCOM_API_KEY_MISSING),
    ],
)
async def test_unusable_connections_fail_with_distinct_codes(
    integration: WorkspaceIntegration | None, code: str
) -> None:
    db = _ScopedDB([integration] if integration else [])

    with pytest.raises(CalComCredentialError) as exc_info:
        await resolve_calcom_credentials(db, WS_A)  # type: ignore[arg-type]

    assert exc_info.value.code == code
    assert "Settings" in exc_info.value.message


async def test_inactive_workspace_connection_does_not_fall_back_to_global(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "calcom_api_key", GLOBAL_KEY, raising=False)
    db = _ScopedDB([_integration(WS_A, {"api_key": KEY_A}, is_active=False)])

    with pytest.raises(CalComCredentialError) as exc_info:
        await resolve_calcom_credentials(db, WS_A)  # type: ignore[arg-type]

    assert exc_info.value.code == CALCOM_INTEGRATION_INACTIVE


# ── Text path ────────────────────────────────────────────────────────────────


async def test_text_gate_and_availability_use_workspace_key(calcom_wire: dict[str, Any]) -> None:
    db = _ScopedDB([_integration(WS_A, {"api_key": KEY_A}), _integration(WS_B, {"api_key": KEY_B})])

    assert await text_booking_enabled(_agent(WS_A), db, WS_A) is True  # type: ignore[arg-type]
    result = await _text_executor(db, WS_B).execute("check_availability", {"start_date": SLOT_DAY})

    assert result["success"] is True, result
    assert result["slot_count"] == 1
    assert calcom_wire["requests"] == [("GET", "/v2/slots/available", KEY_B)]
    # Timezone follows the executor/workspace setting.
    assert calcom_wire["params"][0]["timeZone"] == "America/Denver"


async def test_text_gate_closed_and_tool_actionable_when_not_connected(
    calcom_wire: dict[str, Any],
) -> None:
    db = _ScopedDB([_integration(WS_A, {"api_key": KEY_A})])

    assert await text_booking_enabled(_agent(WS_B), db, WS_B) is False  # type: ignore[arg-type]
    result = await _text_executor(db, WS_B).execute("check_availability", {"start_date": SLOT_DAY})

    assert result["success"] is False
    assert result["error_code"] == CALCOM_NOT_CONNECTED
    assert calcom_wire["requests"] == []


async def test_text_availability_reports_provider_rejection(calcom_wire: dict[str, Any]) -> None:
    calcom_wire["rejected_keys"].add(KEY_A)
    db = _ScopedDB([_integration(WS_A, {"api_key": KEY_A})])

    result = await _text_executor(db, WS_A).execute("check_availability", {"start_date": SLOT_DAY})

    assert result["success"] is False
    assert result["error_code"] == CALCOM_AUTH_FAILED
    assert "Reconnect Cal.com" in result["error"]
    assert KEY_A not in result["error"]


# ── Voice path ───────────────────────────────────────────────────────────────


async def test_voice_books_with_workspace_key(
    calcom_wire: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _ScopedDB([_integration(WS_A, {"api_key": KEY_A}), _integration(WS_B, {"api_key": KEY_B})])
    monkeypatch.setattr(db_session_module, "AsyncSessionLocal", lambda: db)
    executor = VoiceToolExecutor(agent=_agent(WS_A), timezone="UTC")

    offered = await executor.execute("check_availability", {"start_date": SLOT_DAY})
    assert offered["success"] is True, offered
    result = await executor._execute_without_booking_flow(
        "book_appointment",
        {"date": SLOT_DAY, "time": "19:00", "email": "caller@example.test", "name": "Caller"},
    )

    assert result["success"] is True, result
    keys = {key for _method, _path, key in calcom_wire["requests"]}
    assert keys == {KEY_A}
    assert ("POST", "/v2/bookings", KEY_A) in calcom_wire["requests"]


async def test_voice_reports_missing_event_type(
    calcom_wire: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _ScopedDB([_integration(WS_A, {"api_key": KEY_A})])
    monkeypatch.setattr(db_session_module, "AsyncSessionLocal", lambda: db)
    executor = VoiceToolExecutor(agent=_agent(WS_A, calcom_event_type_id=None))

    result = await executor.execute("check_availability", {"start_date": SLOT_DAY})

    assert result["success"] is False
    assert result["error_code"] == CALCOM_EVENT_TYPE_MISSING
    assert calcom_wire["requests"] == []


@pytest.mark.parametrize(
    ("integrations", "expected"),
    [
        ([_integration(WS_A, {"api_key": KEY_A})], True),
        ([_integration(WS_B, {"api_key": KEY_B})], False),
        ([_integration(WS_A, {"api_key": KEY_A}, is_active=False)], False),
    ],
)
async def test_voice_factory_enables_tools_from_workspace_connection(
    integrations: list[WorkspaceIntegration], expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = VoiceSessionFactory(settings)
    captured: dict[str, Any] = {}

    def fake_create_session(
        provider: str, agent: Any, timezone: str, *, calcom_ready: bool | None = None
    ) -> tuple[None, None]:
        captured["enable_tools"] = factory._should_enable_tools(agent, calcom_ready=calcom_ready)
        return None, None

    monkeypatch.setattr(factory, "create_session", fake_create_session)

    await factory.create_session_for_workspace(
        _ScopedDB(integrations),  # type: ignore[arg-type]
        WS_A,
        "grok",
        _agent(WS_A),  # type: ignore[arg-type]
        "UTC",
    )

    assert captured["enable_tools"] is expected


# ── Approval handler ─────────────────────────────────────────────────────────


def _pending_booking(workspace_id: uuid.UUID, agent_id: uuid.UUID | None) -> PendingAction:
    return PendingAction(
        workspace_id=workspace_id,
        agent_id=agent_id,
        action_type="book_appointment",
        action_payload={
            "date": SLOT_DAY,
            "time": "19:00",
            "email": "lead@example.test",
            "name": "Lead",
            # A model-supplied key must never be used.
            "api_key": KEY_A,
        },
        context={"source": "text_conversation", "contact_id": CONTACT_ID},
    )


async def test_approved_booking_uses_actions_workspace_key(
    calcom_wire: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = _agent(WS_B)
    db = _ScopedDB(
        [_integration(WS_A, {"api_key": KEY_A}), _integration(WS_B, {"api_key": KEY_B})],
        agents=[agent],
    )

    async def _tz(_workspace_id: uuid.UUID, _db: Any) -> str:
        return "America/Chicago"

    async def _no_staff(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("app.services.ai.message_context_builder.get_workspace_timezone", _tz)
    monkeypatch.setattr(
        "app.services.calendar.staff_assignment.resolve_staff_for_booking", _no_staff
    )

    result = await BookAppointmentActionHandler().execute(
        db,  # type: ignore[arg-type]
        _pending_booking(WS_B, agent.id),
    )

    assert result["status"] == "booked", result
    assert result["event_type_id"] == 777
    assert {key for _m, _p, key in calcom_wire["requests"]} == {KEY_B}


@pytest.mark.parametrize(
    ("integrations", "rejected", "code"),
    [
        ([], False, CALCOM_NOT_CONNECTED),
        (
            [_integration(WS_B, {"api_key": KEY_B}, is_active=False)],
            False,
            CALCOM_INTEGRATION_INACTIVE,
        ),
        ([_integration(WS_B, {"api_key": KEY_B})], True, CALCOM_AUTH_FAILED),
    ],
)
async def test_approved_booking_failures_are_actionable(
    calcom_wire: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    integrations: list[WorkspaceIntegration],
    rejected: bool,
    code: str,
) -> None:
    if rejected:
        calcom_wire["rejected_keys"].add(KEY_B)
    agent = _agent(WS_B)
    db = _ScopedDB(integrations, agents=[agent])

    async def _tz(_workspace_id: uuid.UUID, _db: Any) -> str:
        return "UTC"

    async def _no_staff(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("app.services.ai.message_context_builder.get_workspace_timezone", _tz)
    monkeypatch.setattr(
        "app.services.calendar.staff_assignment.resolve_staff_for_booking", _no_staff
    )

    result = await BookAppointmentActionHandler().execute(
        db,  # type: ignore[arg-type]
        _pending_booking(WS_B, agent.id),
    )

    assert result["status"] == "failed"
    assert result["error_code"] == code
    assert KEY_B not in result["error"]
    assert code != CALCOM_PROVIDER_ERROR
