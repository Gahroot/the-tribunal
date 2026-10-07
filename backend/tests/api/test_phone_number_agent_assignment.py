"""RF-016: a purchased voice number must have an inbound agent ready (or say why not).

Covers purchase-time assignment for zero / one / several eligible voice agents,
rejection of inactive and wrong-workspace agents before the paid purchase,
readiness reporting, and an inbound call resolving the purchased number's agent.
The Telnyx provider is a test double; nothing is bought or dialled.
"""

from __future__ import annotations

import operator
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import (
    BinaryExpression,
    BindParameter,
    BooleanClauseList,
    False_,
    True_,
)

from app.api.v1 import phone_numbers
from app.models.agent import Agent
from app.models.phone_number import PhoneNumber
from app.schemas.phone_number import PhoneNumberUpdate, PurchasePhoneNumberRequest
from app.services.telephony.telnyx import PhoneNumberInfo
from app.services.telephony.voice_agent_resolver import VoiceAgentResolver

WS = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
OTHER_WS = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
NUMBER = "+15551230000"


# --------------------------------------------------------------------------- #
# Fake session that honours the compiled WHERE clause (workspace scoping etc.)
# --------------------------------------------------------------------------- #


def _literal(element: Any) -> Any:
    if isinstance(element, BindParameter):
        return element.effective_value
    if isinstance(element, True_):
        return True
    if isinstance(element, False_):
        return False
    raise AssertionError(f"unsupported literal {element!r}")


_BINARY_OPS: dict[Any, Any] = {
    operators.eq: operator.eq,
    operators.ne: operator.ne,
    operators.is_: operator.is_,
    operators.is_not: operator.is_not,
    operators.in_op: lambda value, options: value in options,
}


def _matches(row: Any, clause: Any) -> bool:
    if clause is None:
        return True
    if isinstance(clause, BooleanClauseList):
        results = [_matches(row, c) for c in clause.clauses]
        return all(results) if clause.operator is operators.and_ else any(results)
    if isinstance(clause, BinaryExpression):
        op = _BINARY_OPS[clause.operator]
        return bool(op(getattr(row, clause.left.key), _literal(clause.right)))
    raise AssertionError(f"unsupported clause {clause!r}")


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any:
        assert len(self._rows) <= 1, self._rows
        return self._rows[0] if self._rows else None

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class _FakeDB:
    def __init__(self, agents: list[Agent], phones: list[PhoneNumber] | None = None) -> None:
        self.rows: dict[type, list[Any]] = {Agent: list(agents), PhoneNumber: list(phones or [])}
        self.commits = 0

    async def execute(self, query: Any) -> _Result:
        entity = query.column_descriptions[0]["entity"]
        rows = [r for r in self.rows[entity] if _matches(r, query.whereclause)]
        return _Result(rows)

    def add(self, obj: Any) -> None:
        self.rows[type(obj)].append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj: Any) -> None:
        # Apply scalar column defaults the way an INSERT would.
        for column in type(obj).__table__.columns:
            if getattr(obj, column.key) is None and column.default is not None:
                arg = column.default.arg
                setattr(obj, column.key, arg(None) if callable(arg) else arg)


def _agent(
    name: str,
    *,
    workspace_id: uuid.UUID = WS,
    channel_mode: str = "voice",
    active: bool = True,
    age_minutes: int = 0,
) -> Agent:
    return Agent(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name=name,
        channel_mode=channel_mode,
        is_active=active,
        created_at=datetime.now(UTC) - timedelta(minutes=age_minutes),
    )


class _FakeTelnyx:
    purchases: list[str]

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def purchase_phone_number(self, phone_number: str) -> PhoneNumberInfo:
        type(self).purchases.append(phone_number)
        return PhoneNumberInfo(id="tn-test-1", phone_number=phone_number)

    async def close(self) -> None:
        return None


@pytest.fixture
def fake_telnyx(monkeypatch: pytest.MonkeyPatch) -> type[_FakeTelnyx]:
    _FakeTelnyx.purchases = []

    async def _key(_db: Any, _workspace_id: uuid.UUID) -> str:
        return "sandbox-key"

    monkeypatch.setattr(phone_numbers, "get_telnyx_api_key_for_workspace", _key)
    monkeypatch.setattr(phone_numbers, "TelnyxSMSService", _FakeTelnyx)
    return _FakeTelnyx


async def _purchase(db: _FakeDB, **request: Any) -> Any:
    return await phone_numbers.purchase_phone_number(
        workspace_id=WS,
        request_data=PurchasePhoneNumberRequest(phone_number=NUMBER, **request),
        current_user=MagicMock(),
        db=db,  # type: ignore[arg-type]
        workspace=MagicMock(),
    )


# --------------------------------------------------------------------------- #
# Purchase-time assignment
# --------------------------------------------------------------------------- #


async def test_single_eligible_agent_is_assigned_by_default(fake_telnyx: type[_FakeTelnyx]) -> None:
    voice = _agent("Receptionist")
    db = _FakeDB(
        [
            voice,
            _agent("Texter", channel_mode="text"),
            _agent("Retired", active=False),
            _agent("Neighbour", workspace_id=OTHER_WS),
        ]
    )

    response = await _purchase(db)

    assert fake_telnyx.purchases == [NUMBER]
    assert response.assigned_agent_id == voice.id
    assert response.agent_assignment == "default_single_agent"
    assert response.inbound_voice.status == "ready"
    assert response.inbound_voice.ready is True
    assert response.inbound_voice.assigned_agent_name == "Receptionist"


async def test_multiple_eligible_agents_leave_assignment_pending(
    fake_telnyx: type[_FakeTelnyx],
) -> None:
    db = _FakeDB([_agent("Sales"), _agent("Support", channel_mode="both")])

    response = await _purchase(db)

    assert fake_telnyx.purchases == [NUMBER]
    assert response.assigned_agent_id is None
    assert response.agent_assignment == "pending"
    assert response.voice_enabled is True  # provider capability...
    assert response.inbound_voice.ready is False  # ...is not inbound readiness
    assert response.inbound_voice.status == "needs_agent_choice"
    assert response.inbound_voice.eligible_agent_count == 2


async def test_explicit_choice_among_multiple_agents_is_used(
    fake_telnyx: type[_FakeTelnyx],
) -> None:
    sales, support = _agent("Sales"), _agent("Support")
    db = _FakeDB([sales, support])

    response = await _purchase(db, assigned_agent_id=support.id)

    assert response.assigned_agent_id == support.id
    assert response.agent_assignment == "explicit"
    assert response.inbound_voice.status == "ready"


async def test_zero_eligible_agents_reports_recovery_path(
    fake_telnyx: type[_FakeTelnyx],
) -> None:
    db = _FakeDB([_agent("Texter", channel_mode="text")])

    response = await _purchase(db)

    assert response.assigned_agent_id is None
    assert response.agent_assignment == "pending"
    assert response.inbound_voice.status == "no_eligible_agent"
    assert response.inbound_voice.action_href == "/agents/create"


async def test_sms_only_purchase_can_skip_assignment(fake_telnyx: type[_FakeTelnyx]) -> None:
    db = _FakeDB([_agent("Receptionist")])

    response = await _purchase(db, skip_agent_assignment=True)

    assert response.assigned_agent_id is None
    assert response.agent_assignment == "skipped"
    assert response.sms_enabled is True


async def test_text_only_agent_can_be_assigned_for_sms_but_is_not_voice_ready(
    fake_telnyx: type[_FakeTelnyx],
) -> None:
    texter = _agent("Texter", channel_mode="text")
    db = _FakeDB([texter])

    response = await _purchase(db, assigned_agent_id=texter.id)

    assert response.assigned_agent_id == texter.id
    assert response.inbound_voice.status == "agent_not_eligible"
    assert response.inbound_voice.ready is False


@pytest.mark.parametrize(
    "bad_agent",
    [
        pytest.param(_agent("Retired", active=False), id="inactive"),
        pytest.param(_agent("Neighbour", workspace_id=OTHER_WS), id="wrong-workspace"),
    ],
)
async def test_invalid_explicit_agent_is_rejected_before_paid_purchase(
    fake_telnyx: type[_FakeTelnyx], bad_agent: Agent
) -> None:
    db = _FakeDB([bad_agent, _agent("Receptionist")])

    with pytest.raises(HTTPException) as exc_info:
        await _purchase(db, assigned_agent_id=bad_agent.id)

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert fake_telnyx.purchases == []
    assert db.rows[PhoneNumber] == []


# --------------------------------------------------------------------------- #
# Existing assignment action (PUT) and readiness listing
# --------------------------------------------------------------------------- #


def _phone(*, workspace_id: uuid.UUID = WS, agent_id: uuid.UUID | None = None) -> PhoneNumber:
    return PhoneNumber(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        phone_number=NUMBER,
        sms_enabled=True,
        voice_enabled=True,
        is_active=True,
        assigned_agent_id=agent_id,
    )


@pytest.mark.parametrize(
    "bad_agent",
    [
        pytest.param(_agent("Retired", active=False), id="inactive"),
        pytest.param(_agent("Neighbour", workspace_id=OTHER_WS), id="wrong-workspace"),
    ],
)
async def test_update_rejects_inactive_or_foreign_agent(bad_agent: Agent) -> None:
    phone = _phone()
    db = _FakeDB([bad_agent], [phone])

    with pytest.raises(HTTPException) as exc_info:
        await phone_numbers.update_phone_number(
            workspace_id=WS,
            phone_number_id=phone.id,
            phone_number_in=PhoneNumberUpdate(assigned_agent_id=bad_agent.id),
            current_user=MagicMock(),
            db=db,  # type: ignore[arg-type]
            workspace=MagicMock(),
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert phone.assigned_agent_id is None
    assert db.commits == 0


async def test_update_assigns_valid_agent_and_can_clear_it() -> None:
    agent = _agent("Receptionist")
    phone = _phone()
    db = _FakeDB([agent], [phone])
    kwargs: dict[str, Any] = {
        "workspace_id": WS,
        "phone_number_id": phone.id,
        "current_user": MagicMock(),
        "db": db,
        "workspace": MagicMock(),
    }

    await phone_numbers.update_phone_number(
        phone_number_in=PhoneNumberUpdate(assigned_agent_id=agent.id), **kwargs
    )
    assert phone.assigned_agent_id == agent.id

    await phone_numbers.update_phone_number(
        phone_number_in=PhoneNumberUpdate(assigned_agent_id=None), **kwargs
    )
    assert phone.assigned_agent_id is None


async def test_readiness_lists_only_workspace_numbers_and_flags_foreign_agent() -> None:
    sales, support = _agent("Sales", age_minutes=5), _agent("Support")
    foreign_agent = _agent("Neighbour", workspace_id=OTHER_WS)
    ready_phone = _phone(agent_id=sales.id)
    pending_phone = _phone()
    foreign_assigned = _phone(agent_id=foreign_agent.id)
    other_ws_phone = _phone(workspace_id=OTHER_WS, agent_id=foreign_agent.id)
    db = _FakeDB(
        [sales, support, foreign_agent],
        [ready_phone, pending_phone, foreign_assigned, other_ws_phone],
    )

    response = await phone_numbers.get_phone_numbers_inbound_readiness(
        workspace_id=WS,
        current_user=MagicMock(),
        db=db,  # type: ignore[arg-type]
        workspace=MagicMock(),
    )

    assert [a.name for a in response.eligible_agents] == ["Sales", "Support"]
    by_id = {r.phone_number_id: r for r in response.numbers}
    assert set(by_id) == {ready_phone.id, pending_phone.id, foreign_assigned.id}
    assert by_id[ready_phone.id].status == "ready"
    assert by_id[pending_phone.id].status == "needs_agent_choice"
    assert by_id[foreign_assigned.id].status == "agent_not_eligible"
    assert by_id[foreign_assigned.id].assigned_agent_name is None


# --------------------------------------------------------------------------- #
# Inbound call resolution
# --------------------------------------------------------------------------- #


async def test_inbound_call_resolves_purchased_numbers_default_agent(
    fake_telnyx: type[_FakeTelnyx],
) -> None:
    voice = _agent("Receptionist")
    db = _FakeDB([voice])

    await _purchase(db)
    [phone_record] = db.rows[PhoneNumber]

    resolved = await VoiceAgentResolver().resolve(db, None, phone_record, MagicMock())  # type: ignore[arg-type]

    assert resolved is not None
    assert resolved.agent.id == voice.id
    assert resolved.source == "phone_number_agent"


async def test_inbound_call_ignores_agent_from_another_workspace() -> None:
    foreign_agent = _agent("Neighbour", workspace_id=OTHER_WS)
    phone_record = _phone(agent_id=foreign_agent.id)
    db = _FakeDB([foreign_agent], [phone_record])

    resolved = await VoiceAgentResolver().resolve(db, None, phone_record, MagicMock())  # type: ignore[arg-type]

    assert resolved is None
