"""Typed approval command-handler coverage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.pending_action import PendingAction
from app.services.approval.approval_delivery_service import (
    ApprovalDeliveryRequest,
    ApprovalDeliveryResult,
    ApprovalDeliveryService,
)
from app.services.approval.approval_gate_service import (
    ApprovalActionExecutionError,
    ApprovalGateService,
)
from app.services.approval.command_processor_service import CommandProcessorService
from app.workers.approval_worker import ApprovalWorker


class _ScalarResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _ExecuteResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return self._rows[0]

    def scalars(self) -> _ScalarResult:
        return _ScalarResult(self._rows)


class _RecordingActionHandler:
    action_type = "custom.approval_action"

    def __init__(self) -> None:
        self.calls: list[PendingAction] = []

    async def execute(self, db: Any, action: PendingAction) -> dict[str, Any]:
        self.calls.append(action)
        return {"status": "handled", "payload": action.action_payload}


class _FailingActionHandler:
    action_type = "custom.failing_action"

    async def execute(self, db: Any, action: PendingAction) -> dict[str, Any]:
        raise RuntimeError("provider unavailable")


class _RecordingDeliveryHandler:
    def __init__(self, *, channel: str, delivered: bool) -> None:
        self.channel = channel
        self.delivered = delivered
        self.requests: list[ApprovalDeliveryRequest] = []

    async def deliver(
        self,
        db: Any,
        request: ApprovalDeliveryRequest,
    ) -> ApprovalDeliveryResult:
        self.requests.append(request)
        return ApprovalDeliveryResult(channel=self.channel, delivered=self.delivered)


class _RecordingSmsResponder:
    def __init__(self) -> None:
        self.responses: list[dict[str, str]] = []

    async def send_response(self, *, from_number: str, to_number: str, body: str) -> None:
        self.responses.append(
            {
                "from_number": from_number,
                "to_number": to_number,
                "body": body,
            }
        )


def _make_action(*, action_type: str, status: str = "approved") -> PendingAction:
    return PendingAction(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        action_type=action_type,
        action_payload={"message": "hello"},
        description="Send a follow-up",
        context={},
        status=status,
    )


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_typed_approved_action_handler_executes_and_records_result() -> None:
    handler = _RecordingActionHandler()
    service = ApprovalGateService(action_handlers=(handler,))
    action = _make_action(action_type=handler.action_type)
    db = _mock_db()

    result = await service.execute_approved_action(db, action)

    assert result == {"status": "handled", "payload": {"message": "hello"}}
    assert handler.calls == [action]
    assert action.status == "executed"
    assert action.executed_at is not None
    assert action.execution_result == result
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_typed_action_handler_failure_is_retryable() -> None:
    service = ApprovalGateService(action_handlers=(_FailingActionHandler(),))
    action = _make_action(action_type="custom.failing_action")
    db = _mock_db()

    with pytest.raises(ApprovalActionExecutionError):
        await service.execute_approved_action(db, action)

    assert action.status == "approved"
    assert action.executed_at is None
    assert action.execution_result is None
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejected_action_is_not_dispatched_to_handler() -> None:
    handler = _RecordingActionHandler()
    service = ApprovalGateService(action_handlers=(handler,))
    action = _make_action(action_type=handler.action_type, status="rejected")
    db = _mock_db()

    result = await service.execute_approved_action(db, action)

    assert result == {
        "error": "action_not_approved",
        "action_id": str(action.id),
        "status": "rejected",
    }
    assert handler.calls == []
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_handlers_mark_notification_sent_when_any_channel_succeeds() -> None:
    sms_handler = _RecordingDeliveryHandler(channel="sms", delivered=False)
    push_handler = _RecordingDeliveryHandler(channel="push", delivered=True)
    service = ApprovalDeliveryService(channel_handlers=(sms_handler, push_handler))
    action = _make_action(action_type="send_sms", status="pending")
    action.notification_sent = False
    action.notification_sent_at = None
    profile = SimpleNamespace(phone_number="+12025550123")
    agent = SimpleNamespace(name="Front Desk")
    db = _mock_db()
    db.execute = AsyncMock(side_effect=[_ExecuteResult([profile]), _ExecuteResult([agent])])

    ok = await service.notify_pending_action(db, action)

    assert ok is True
    assert action.notification_sent is True
    assert action.notification_sent_at is not None
    assert [request.agent_name for request in sms_handler.requests] == ["Front Desk"]
    assert [request.action for request in push_handler.requests] == [action]
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_pending_action_is_rejected_by_timeout_handler() -> None:
    worker = ApprovalWorker()
    expired_action = _make_action(action_type="send_sms", status="pending")
    expired_action.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db = _mock_db()
    db.execute = AsyncMock(side_effect=[_ExecuteResult([]), _ExecuteResult([expired_action])])

    await worker._handle_timeouts(db)

    assert expired_action.status == "rejected"
    assert expired_action.review_channel == "timeout"
    assert expired_action.reviewed_at is not None
    assert expired_action.rejection_reason == "Approval request timed out."
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sms_approve_command_executes_handler_and_replies() -> None:
    workspace_id = uuid.uuid4()
    action = _make_action(action_type="send_sms", status="pending")
    action.workspace_id = workspace_id
    gate_service = MagicMock()
    gate_service.approve_action = AsyncMock(return_value=action)
    responder = _RecordingSmsResponder()
    db = _mock_db()
    db.execute = AsyncMock(
        side_effect=[
            _ExecuteResult([SimpleNamespace(workspace_id=workspace_id)]),
            _ExecuteResult([SimpleNamespace(phone_number="+12025550100")]),
            _ExecuteResult([action]),
            _ExecuteResult([42]),
        ]
    )
    service = CommandProcessorService(
        gate_service=gate_service,
        sms_responder=responder,
        phone_normalizer=lambda value: value,
    )

    consumed = await service.try_process_command(
        db,
        from_number="+12025550100",
        to_number="+12025550199",
        body="YES",
    )

    assert consumed is True
    gate_service.approve_action.assert_awaited_once_with(
        db,
        action_id=action.id,
        user_id=42,
        channel="sms",
    )
    assert responder.responses == [
        {
            "from_number": "+12025550199",
            "to_number": "+12025550100",
            "body": "✓ Approved: Send a follow-up",
        }
    ]


@pytest.mark.asyncio
async def test_sms_reject_command_executes_handler_and_replies() -> None:
    workspace_id = uuid.uuid4()
    action = _make_action(action_type="send_sms", status="pending")
    action.workspace_id = workspace_id
    gate_service = MagicMock()
    gate_service.reject_action = AsyncMock(return_value=action)
    responder = _RecordingSmsResponder()
    db = _mock_db()
    db.execute = AsyncMock(
        side_effect=[
            _ExecuteResult([SimpleNamespace(workspace_id=workspace_id)]),
            _ExecuteResult([SimpleNamespace(phone_number="+12025550100")]),
            _ExecuteResult([action]),
            _ExecuteResult([42]),
        ]
    )
    service = CommandProcessorService(
        gate_service=gate_service,
        sms_responder=responder,
        phone_normalizer=lambda value: value,
    )

    consumed = await service.try_process_command(
        db,
        from_number="+12025550100",
        to_number="+12025550199",
        body="no",
    )

    assert consumed is True
    gate_service.reject_action.assert_awaited_once_with(
        db,
        action_id=action.id,
        user_id=42,
        channel="sms",
    )
    assert responder.responses == [
        {
            "from_number": "+12025550199",
            "to_number": "+12025550100",
            "body": "✗ Rejected: Send a follow-up",
        }
    ]
