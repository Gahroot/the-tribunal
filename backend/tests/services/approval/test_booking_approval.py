"""RF-015: operator-approved AI booking requests.

The real approval gate, booking handler, credential resolver, BookingService
and CalComService run end to end. Two boundaries are stubbed:

* the database — an in-memory session that evaluates each statement's WHERE
  criteria against stored rows and models ``FOR UPDATE SKIP LOCKED`` claims;
* the Cal.com HTTP API — ``httpx.MockTransport`` behind the real provider client.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, BooleanClauseList, Null

from app.core.config import settings
from app.core.encryption import encrypt_json
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.pending_action import PendingAction
from app.models.workspace import Workspace, WorkspaceIntegration
from app.services.approval.approval_gate_service import (
    ApprovalGateService,
    ApprovalRetryError,
)
from app.services.calendar.calcom_credentials import CALCOM_NOT_CONNECTED
from app.services.providers.http import AsyncProviderHTTPClient

WORKSPACE = uuid.UUID("dddddddd-0000-4000-8000-000000000015")
OTHER_WORKSPACE = uuid.UUID("eeeeeeee-0000-4000-8000-000000000015")
API_KEY = "cal_live_rf015_secret"
TZ = "America/Chicago"
SLOT_DAY = (datetime.now(UTC) + timedelta(days=21)).strftime("%Y-%m-%d")


def _slot_iso(time_str: str, day: str = SLOT_DAY) -> str:
    local = datetime.strptime(f"{day} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(TZ))
    return local.isoformat(timespec="milliseconds")


# ── In-memory session ────────────────────────────────────────────────────────


class _Store:
    def __init__(self) -> None:
        self.rows: dict[type, list[Any]] = {}
        self.locks: dict[uuid.UUID, int] = {}
        self._next_id = 1000

    def add(self, row: Any) -> None:
        self.rows.setdefault(type(row), []).append(row)

    def next_id(self) -> int:
        self._next_id += 1
        return self._next_id


_OPS: dict[Any, Callable[[Any, Any], bool]] = {
    operators.eq: lambda a, b: a == b,
    operators.ne: lambda a, b: a != b,
    operators.is_: lambda a, b: a is b,
    operators.is_not: lambda a, b: a is not b,
}


def _matches(row: Any, criterion: Any) -> bool:
    if isinstance(criterion, BooleanClauseList):
        return all(_matches(row, c) for c in criterion.clauses)
    assert isinstance(criterion, BinaryExpression), criterion
    value = getattr(row, criterion.left.key)
    right = criterion.right
    if isinstance(right, Null):
        expected = None
    elif isinstance(right, BindParameter):
        expected = right.effective_value
    else:  # true()/false() literals
        expected = {"true": True, "false": False}.get(str(right), right)
    return _OPS[criterion.operator](value, expected)


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any | None:
        assert len(self._rows) <= 1
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        assert len(self._rows) == 1
        return self._rows[0]

    def scalars(self) -> _Result:
        return self

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


class _Nested:
    def __init__(self, session: _Session) -> None:
        self._session = session
        self._mark = 0

    async def __aenter__(self) -> None:
        self._mark = len(self._session.pending)

    async def __aexit__(self, exc_type: Any, *_rest: Any) -> bool:
        if exc_type is not None:
            del self._session.pending[self._mark :]
        return False


class _Session:
    """Each session is one transaction; locks are released on commit/rollback."""

    def __init__(self, store: _Store, *, fail_flush: bool = False) -> None:
        self.store = store
        self.pending: list[Any] = []
        self.fail_flush = fail_flush
        self.commits = 0

    async def execute(self, query: Any) -> _Result:
        entity = query.column_descriptions[0]["entity"]
        rows = [
            r
            for r in self.store.rows.get(entity, [])
            if all(_matches(r, c) for c in query._where_criteria)
        ]
        lock = query._for_update_arg
        if lock is not None:
            mine = id(self)
            if lock.skip_locked:
                rows = [r for r in rows if self.store.locks.get(r.id, mine) == mine]
            for r in rows:
                assert self.store.locks.get(r.id, mine) == mine, "lock wait would deadlock test"
                self.store.locks[r.id] = mine
        return _Result(rows)

    def add(self, row: Any) -> None:
        self.pending.append(row)

    def begin_nested(self) -> _Nested:
        return _Nested(self)

    async def flush(self) -> None:
        if self.fail_flush and any(isinstance(r, Appointment) for r in self.pending):
            raise RuntimeError("database unavailable")
        for row in self.pending:
            if isinstance(row, Appointment) and row.id is None:
                row.id = self.store.next_id()
            self.store.add(row)
        self.pending.clear()

    def _release(self) -> None:
        self.store.locks = {k: v for k, v in self.store.locks.items() if v != id(self)}

    async def commit(self) -> None:
        await self.flush()
        self.commits += 1
        self._release()

    async def rollback(self) -> None:
        self.pending.clear()
        self._release()

    async def refresh(self, _row: Any) -> None:
        return None


# ── Cal.com boundary ─────────────────────────────────────────────────────────


@pytest.fixture
def calcom(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {
        "slots": ["19:00", "20:00"],
        "booking_status": 201,
        "requests": [],
        "booked": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v2/slots/available":
            assert request.url.params["timeZone"] == TZ
            slots = [{"time": _slot_iso(t)} for t in state["slots"]]
            return httpx.Response(
                200, json={"status": "success", "data": {"slots": {SLOT_DAY: slots}}}
            )
        if request.method == "POST" and request.url.path == "/v2/bookings":
            if state["booking_status"] >= 400:
                return httpx.Response(state["booking_status"], json={"message": "upstream down"})
            body = json.loads(request.content)
            state["booked"].append(body)
            uid = f"uid-{len(state['booked'])}"
            return httpx.Response(201, json={"status": "success", "data": {"uid": uid, "id": 42}})
        return httpx.Response(404, json={"message": "not found"})

    class WireClient(AsyncProviderHTTPClient):
        def __init__(self, **kwargs: Any) -> None:
            kwargs.pop("retry_policy", None)
            super().__init__(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("app.services.calendar.calcom.AsyncProviderHTTPClient", WireClient)
    monkeypatch.setattr(settings, "calcom_api_key", "", raising=False)
    return state


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _seed(*, connected: bool = True) -> tuple[_Store, PendingAction]:
    store = _Store()
    store.add(Workspace(id=WORKSPACE, name="RF-015", slug="rf-015", settings={"timezone": TZ}))
    if connected:
        store.add(
            WorkspaceIntegration(
                id=uuid.uuid4(),
                workspace_id=WORKSPACE,
                integration_type="calcom",
                encrypted_credentials=encrypt_json({"api_key": API_KEY}),
                is_active=True,
            )
        )
    agent = Agent(
        id=uuid.uuid4(),
        workspace_id=WORKSPACE,
        name="Closer",
        calcom_event_type_id=777,
        assignment_strategy="single",
    )
    store.add(agent)
    store.add(
        Contact(
            id=501,
            workspace_id=WORKSPACE,
            first_name="Test",
            last_name="Lead",
            email="test.lead@example.test",
            phone_number="+15555550100",
        )
    )
    # Same id in another workspace must never be used.
    store.add(Contact(id=502, workspace_id=OTHER_WORKSPACE, first_name="Other"))
    action = PendingAction(
        id=uuid.uuid4(),
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        action_type="book_appointment",
        action_payload={
            "date": SLOT_DAY,
            "time": "19:00",
            "email": "test.lead@example.test",
            "name": "Model Supplied Name",
            "api_key": "cal_live_model_injected",
        },
        description="book_appointment",
        context={"source": "text_conversation", "contact_id": 501},
        status="pending",
    )
    store.add(action)
    return store, action


async def _approve_and_run(
    store: _Store, action: PendingAction, service: ApprovalGateService
) -> dict[str, Any]:
    approver = _Session(store)
    await service.approve_action(approver, action.id, user_id=7)
    worker = _Session(store)
    return await service.execute_approved_action(worker, action)


def _appointments(store: _Store) -> list[Appointment]:
    return store.rows.get(Appointment, [])


# ── Cases ────────────────────────────────────────────────────────────────────


async def test_approved_booking_books_and_persists_appointment(
    calcom: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    store, action = _seed()

    result = await _approve_and_run(store, action, ApprovalGateService())

    assert result["status"] == "booked", result
    assert action.status == "executed"
    [appointment] = _appointments(store)
    assert result["appointment_id"] == appointment.id
    assert appointment.workspace_id == WORKSPACE
    assert appointment.contact_id == 501
    assert appointment.calcom_booking_uid == "uid-1"
    assert appointment.scheduled_at == datetime.fromisoformat(_slot_iso("19:00"))
    [booked] = calcom["booked"]
    assert booked["eventTypeId"] == 777
    assert booked["start"] == _slot_iso("19:00")
    # Attendee comes from the trusted contact record, not model arguments.
    assert booked["attendee"]["name"] == "Test Lead"
    assert booked["attendee"]["timeZone"] == TZ
    # Credentials never leak into results or logs.
    assert API_KEY not in json.dumps(result, default=str)
    assert API_KEY not in capsys.readouterr().out


async def test_absent_calendar_configuration_fails_honestly_and_retries(
    calcom: dict[str, Any],
) -> None:
    store, action = _seed(connected=False)
    service = ApprovalGateService()

    result = await _approve_and_run(store, action, service)

    assert action.status == "failed"
    assert result["error_code"] == CALCOM_NOT_CONNECTED
    assert result["retryable"] is True
    assert "booked" not in json.dumps(result)
    assert calcom["requests"] == []
    assert _appointments(store) == []

    # Operator connects Cal.com, then retries the same request.
    store.add(
        WorkspaceIntegration(
            id=uuid.uuid4(),
            workspace_id=WORKSPACE,
            integration_type="calcom",
            encrypted_credentials=encrypt_json({"api_key": API_KEY}),
            is_active=True,
        )
    )
    await service.retry_failed_action(
        _Session(store), workspace_id=WORKSPACE, action_id=action.id, user_id=7
    )
    assert action.status == "approved"
    result = await service.execute_approved_action(_Session(store), action)
    assert result["status"] == "booked"
    assert action.status == "executed"
    assert len(_appointments(store)) == 1


async def test_provider_failure_stays_failed_and_retryable(calcom: dict[str, Any]) -> None:
    store, action = _seed()
    calcom["booking_status"] = 500
    service = ApprovalGateService()

    result = await _approve_and_run(store, action, service)

    assert action.status == "failed"
    assert result["status"] == "failed"
    assert result["retryable"] is True
    assert _appointments(store) == []

    calcom["booking_status"] = 201
    await service.retry_failed_action(
        _Session(store), workspace_id=WORKSPACE, action_id=action.id, user_id=7
    )
    result = await service.execute_approved_action(_Session(store), action)
    assert result["status"] == "booked"
    assert action.context["retry_count"] == 1
    assert len(_appointments(store)) == 1


async def test_stale_slot_offers_alternatives_and_rebooks_chosen_slot(
    calcom: dict[str, Any],
) -> None:
    store, action = _seed()
    calcom["slots"] = ["20:00", "21:00"]  # 19:00 was taken after the proposal
    service = ApprovalGateService()

    result = await _approve_and_run(store, action, service)

    assert action.status == "failed"
    assert result["error_code"] == "booking_slot_unavailable"
    assert result["requested_slot"] == {"date": SLOT_DAY, "time": "19:00"}
    assert {"date": SLOT_DAY, "time": "20:00"} in result["alternative_slots"]
    assert calcom["booked"] == []

    await service.retry_failed_action(
        _Session(store),
        workspace_id=WORKSPACE,
        action_id=action.id,
        user_id=7,
        slot=(SLOT_DAY, "20:00"),
    )
    assert action.context["requested_slot"] == {"date": SLOT_DAY, "time": "19:00"}
    result = await service.execute_approved_action(_Session(store), action)
    assert result["status"] == "booked"
    [appointment] = _appointments(store)
    assert appointment.scheduled_at == datetime.fromisoformat(_slot_iso("20:00"))


async def test_repeated_approval_and_execution_book_once(calcom: dict[str, Any]) -> None:
    store, action = _seed()
    service = ApprovalGateService()

    await _approve_and_run(store, action, service)
    # A second approval (double click, SMS "YES" twice) leaves it executed.
    again = await service.approve_action(_Session(store), action.id, user_id=8)
    assert again.status == "executed"
    replay = await service.execute_approved_action(_Session(store), action)
    assert replay["error"] == "action_not_approved"
    with pytest.raises(ApprovalRetryError):
        await service.retry_failed_action(
            _Session(store), workspace_id=WORKSPACE, action_id=action.id, user_id=7
        )

    assert len(calcom["booked"]) == 1
    assert len(_appointments(store)) == 1


async def test_concurrent_executor_cannot_claim_a_locked_action(calcom: dict[str, Any]) -> None:
    store, action = _seed()
    service = ApprovalGateService()
    await service.approve_action(_Session(store), action.id, user_id=7)

    first = _Session(store)
    assert await service._claim_for_execution(first, action) is True
    second = _Session(store)
    result = await service.execute_approved_action(second, action)

    assert result["error"] == "action_not_claimed"
    assert calcom["booked"] == []


async def test_existing_provider_booking_is_not_duplicated(calcom: dict[str, Any]) -> None:
    store, action = _seed()
    # e.g. the Cal.com webhook already recorded the booking from an earlier attempt
    store.add(
        Appointment(
            id=900,
            workspace_id=WORKSPACE,
            contact_id=501,
            scheduled_at=datetime.fromisoformat(_slot_iso("19:00")),
            duration_minutes=30,
            status="scheduled",
            calcom_booking_uid="uid-webhook",
        )
    )

    result = await _approve_and_run(store, action, ApprovalGateService())

    assert result["status"] == "booked"
    assert result["deduplicated"] is True
    assert result["appointment_id"] == 900
    assert calcom["booked"] == []


async def test_persist_failure_after_provider_success_is_not_retryable(
    calcom: dict[str, Any],
) -> None:
    store, action = _seed()
    service = ApprovalGateService()
    await service.approve_action(_Session(store), action.id, user_id=7)

    result = await service.execute_approved_action(_Session(store, fail_flush=True), action)

    assert action.status == "failed"
    assert result["error_code"] == "booking_persist_failed"
    assert result["retryable"] is False
    assert result["booking_uid"] == "uid-1"
