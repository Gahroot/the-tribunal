"""Automation execution outcomes (RF-013).

Covers the operator's first-use path - the default Send SMS automation -
through real worker dispatch and the shared ``OutboundDeliveryService``
(compliance + provider) with a captured fake provider, plus failure feedback:
missing templates or prerequisites must fail the execution with an actionable
error instead of completing as a silent no-op. No real sends happen.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.automations import _to_response
from app.models.automation import Automation
from app.models.automation_execution import AutomationExecution
from app.models.conversation import Message
from app.services.telephony.text_delivery import require_text_accepted
from app.workers.automation_worker import AutomationWorker

WORKSPACE_ID = uuid.uuid4()
FROM_NUMBER = "+15550001111"


class FakeTextProvider:
    """Captures sends instead of hitting Telnyx."""

    def __init__(self, status: str = "sent", error: str | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self._status = status
        self._error = error

    async def send_message(self, **kwargs: Any) -> Message:
        self.sent.append(kwargs)
        message = SimpleNamespace(
            id=uuid.uuid4(),
            status=self._status,
            provider_message_id="fake-1",
            error_message=self._error,
        )
        return require_text_accepted(cast(Message, message))

    async def close(self) -> None:
        return None


def _automation(actions: list[dict[str, Any]], trigger: str = "no_show") -> Automation:
    now = datetime.now(UTC)
    return Automation(
        created_at=now,
        updated_at=now,
        last_triggered_at=None,
        description=None,
        id=uuid.uuid4(),
        workspace_id=WORKSPACE_ID,
        name="No-show follow-up",
        trigger_type=trigger,
        trigger_config={},
        actions=actions,
        is_active=True,
    )


def _contact(**overrides: Any) -> MagicMock:
    contact = MagicMock()
    contact.id = 42
    contact.workspace_id = WORKSPACE_ID
    contact.first_name = "Ada"
    contact.last_name = "Lovelace"
    contact.company_name = "Analytical"
    contact.email = "ada@example.com"
    contact.phone_number = "+15551230000"
    contact.sms_consent_status = "unknown"
    for key, value in overrides.items():
        setattr(contact, key, value)
    return contact


def _execution(automation: Automation) -> AutomationExecution:
    return AutomationExecution(
        id=uuid.uuid4(),
        automation_id=automation.id,
        contact_id=42,
        status="pending",
        created_at=datetime.now(UTC),
    )


@pytest.fixture(autouse=True)
def _auto_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.workers.automation_worker as mod

    monkeypatch.setattr(
        mod.approval_gate_service,
        "check_and_execute_or_queue",
        AsyncMock(return_value=("auto", None)),
    )
    # Notifications are a side effect outside this test's scope.
    monkeypatch.setattr(AutomationWorker, "_notify_automation_triggered", AsyncMock())


async def _run(
    automation: Automation,
    contact: Any,
    *,
    provider: FakeTextProvider | None = None,
    opted_out: bool = False,
    from_number: str | None = FROM_NUMBER,
) -> tuple[AutomationExecution, FakeTextProvider]:
    provider = provider or FakeTextProvider()
    worker = AutomationWorker()
    execution = _execution(automation)
    with (
        patch(
            "app.workers.automation_worker.get_text_message_provider",
            lambda *_a, **_k: provider,
        ),
        patch(
            "app.services.rate_limiting.opt_out_manager.OptOutManager.check_opt_out",
            AsyncMock(return_value=opted_out),
        ),
        patch.object(worker, "_resolve_from_number", AsyncMock(return_value=from_number)),
    ):
        await worker._run_actions(automation, contact, {}, execution, MagicMock())
    return execution, provider


async def test_configured_default_sms_automation_sends_and_completes() -> None:
    automation = _automation(
        [{"type": "send_sms", "config": {"message": "Hi {first_name}, want to rebook?"}}]
    )

    execution, provider = await _run(automation, _contact())

    assert execution.status == "completed"
    assert execution.error is None
    assert len(provider.sent) == 1
    assert provider.sent[0]["to_number"] == "+15551230000"
    assert provider.sent[0]["from_number"] == FROM_NUMBER
    assert provider.sent[0]["body"] == "Hi Ada, want to rebook?"
    assert provider.sent[0]["idempotency_key"] is not None

    response = _to_response(automation, execution)
    assert response.readiness == "ready"
    assert response.last_execution is not None
    assert response.last_execution.status == "completed"


async def test_unconfigured_default_sms_automation_fails_visibly() -> None:
    """A legacy active row with the empty default never reports success."""
    automation = _automation([{"type": "send_sms", "config": {}}])

    execution, provider = await _run(automation, _contact())

    assert provider.sent == []
    assert execution.status == "failed"
    assert "write the text message to send" in (execution.error or "")

    response = _to_response(automation, execution)
    assert response.readiness == "incomplete"
    assert response.last_execution is not None
    assert response.last_execution.status == "failed"
    assert response.last_execution.error == execution.error


@pytest.mark.parametrize(
    ("kwargs", "contact_overrides", "expected_error"),
    [
        ({"from_number": None}, {}, "No SMS-enabled phone number"),
        ({}, {"phone_number": None}, "no phone number"),
        ({"opted_out": True}, {}, "blocked by compliance checks (global_opt_out)"),
        (
            {"provider": FakeTextProvider(status="failed", error="carrier rejected")},
            {},
            "Check the recipient, sender configuration and messaging permissions before retrying.",
        ),
    ],
)
async def test_sms_prerequisite_failures_are_recorded(
    kwargs: dict[str, Any], contact_overrides: dict[str, Any], expected_error: str
) -> None:
    automation = _automation([{"type": "send_sms", "config": {"message": "Hi"}}])

    execution, _ = await _run(automation, _contact(**contact_overrides), **kwargs)

    assert execution.status == "failed"
    assert expected_error in (execution.error or "")
    assert "carrier rejected" not in (execution.error or "")
    assert execution.executed_at is not None


async def test_email_provider_unavailable_fails_execution() -> None:
    automation = _automation(
        [{"type": "send_email", "config": {"subject": "Hi", "message": "Hello {first_name}"}}]
    )
    with patch(
        "app.workers.automation_worker.send_automation_email", AsyncMock(return_value=False)
    ) as send:
        execution, _ = await _run(automation, _contact())

    send.assert_awaited_once()
    assert send.await_args.kwargs["body"] == "Hello Ada"
    assert send.await_args.kwargs["workspace_id"] == automation.workspace_id
    assert send.await_args.kwargs["db"] is not None
    assert execution.status == "failed"
    assert "email provider" in (execution.error or "")


async def test_email_without_contact_address_fails_execution() -> None:
    automation = _automation(
        [{"type": "send_email", "config": {"subject": "Hi", "message": "Hello"}}]
    )
    with patch("app.workers.automation_worker.send_automation_email", AsyncMock()) as send:
        execution, _ = await _run(automation, _contact(email=None))

    send.assert_not_awaited()
    assert execution.status == "failed"
    assert "no email address" in (execution.error or "")


async def test_email_cross_brand_contact_is_rejected_before_sending() -> None:
    automation = _automation(
        [{"type": "send_email", "config": {"subject": "Hi", "message": "Hello"}}]
    )
    with patch("app.workers.automation_worker.send_automation_email", AsyncMock()) as send:
        execution, _ = await _run(automation, _contact(workspace_id=uuid.uuid4()))
    send.assert_not_awaited()
    assert execution.status == "failed"
    assert "does not belong to this brand" in execution.error


async def test_apply_tag_action_completes() -> None:
    automation = _automation([{"type": "apply_tag", "config": {"tag": "no-show"}}])
    with patch("app.workers.automation_worker.TagService") as tag_service:
        tag_service.return_value.add_tag_to_contact = AsyncMock()
        execution, _ = await _run(automation, _contact())

    tag_service.return_value.add_tag_to_contact.assert_awaited_once()
    assert execution.status == "completed"


async def test_enroll_in_missing_campaign_fails_execution() -> None:
    automation = _automation(
        [{"type": "enroll_campaign", "config": {"campaign_id": str(uuid.uuid4())}}]
    )
    worker = AutomationWorker()
    execution = _execution(automation)
    db = MagicMock()
    missing = MagicMock()
    missing.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=missing)

    await worker._run_actions(automation, _contact(), {}, execution, db)

    assert execution.status == "failed"
    assert "campaign was deleted or is not running" in (execution.error or "")


async def test_failure_in_second_action_is_not_reported_as_success() -> None:
    automation = _automation(
        [
            {"type": "send_sms", "config": {"message": "Hi"}},
            {"type": "send_email", "config": {"subject": "S", "message": "B"}},
        ]
    )
    with patch(
        "app.workers.automation_worker.send_automation_email", AsyncMock(return_value=False)
    ):
        execution, provider = await _run(automation, _contact())

    assert len(provider.sent) == 1
    assert execution.status == "failed"


@pytest.mark.parametrize("call_status", ["failed", "ringing", "completed", "queued"])
async def test_make_call_honors_returned_status(call_status: str) -> None:
    """A returned failed Message is not an exception, but must fail execution."""
    automation = _automation([{"type": "make_call", "config": {}}])
    provider = SimpleNamespace(
        initiate_call=AsyncMock(
            return_value=SimpleNamespace(
                status=call_status,
                error_code="API_ERROR",
                error_message="raw provider dump with credentials",
            )
        ),
        close=AsyncMock(),
    )
    with (
        patch("app.workers.automation_worker.settings.telnyx_api_key", "test-only"),
        patch("app.workers.automation_worker.TelnyxVoiceService", return_value=provider),
    ):
        execution, _ = await _run(automation, _contact())

    accepted = call_status in {"ringing", "completed"}
    assert execution.status == ("completed" if accepted else "failed")
    assert execution.executed_at is not None
    if accepted:
        assert execution.error is None
    else:
        assert "Call was not accepted" in execution.error
        assert "try again" in execution.error
        assert "credentials" not in execution.error
    assert provider.initiate_call.await_args.kwargs["idempotency_key"] is not None
    provider.close.assert_awaited_once()


class SimulatedWorkerCrash(BaseException):
    """Process loss after acceptance, before the execution transaction commits."""


def _assert_retry_steps(
    interrupted: AutomationExecution,
    completed: AutomationExecution,
    attempts: list[uuid.UUID],
    accepted: set[uuid.UUID],
) -> None:
    assert interrupted.id == completed.id
    assert completed.status == "completed"
    assert attempts[0] == attempts[1]  # acceptance-before-crash retry
    assert attempts[1] != attempts[2]  # identical text, different steps
    assert len(accepted) == 2


@pytest.mark.parametrize("channel", ["sms", "email"])
@pytest.mark.parametrize("trigger_path", ["event", "poll"])
async def test_send_steps_survive_crash_and_distinguish_executions(
    channel: str, trigger_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real dispatch, with isolated providers that dedupe accepted retry keys."""
    from app.models.automation_event import AutomationEvent
    from app.services import email

    automation = _automation(
        [
            {"type": f"send_{channel}", "config": {"subject": "Hi", "message": "Hello"}},
            {"type": f"send_{channel}", "config": {"subject": "Hi", "message": "Hello"}},
        ]
    )
    worker = AutomationWorker()
    contact = _contact()
    db = MagicMock()
    # No committed execution: model a rollback after each interrupted attempt.
    db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    db.flush = AsyncMock()
    attempts: list[uuid.UUID] = []
    accepted: set[uuid.UUID] = set()
    crash = True

    def accept(key: uuid.UUID, workspace_id: uuid.UUID) -> None:
        nonlocal crash
        assert workspace_id == WORKSPACE_ID
        attempts.append(key)
        accepted.add(key)
        if crash:
            crash = False
            raise SimulatedWorkerCrash()

    class DedupingTextProvider(FakeTextProvider):
        async def send_message(self, **kwargs: Any) -> Message:
            accept(kwargs["idempotency_key"], kwargs["workspace_id"])
            return await super().send_message(**kwargs)

    async def send_email(params: dict[str, Any], **kwargs: Any) -> dict[str, str]:
        assert params["to"] == [contact.email]
        assert kwargs["db"] is db
        accept(kwargs["idempotency_key"], kwargs["workspace_id"])
        return {"id": "fixture-email"}

    monkeypatch.setattr(
        "app.workers.automation_worker.get_text_message_provider",
        lambda *_a, **_k: DedupingTextProvider(),
    )
    monkeypatch.setattr(
        "app.services.rate_limiting.opt_out_manager.OptOutManager.check_opt_out",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(worker, "_resolve_from_number", AsyncMock(return_value=FROM_NUMBER))
    monkeypatch.setattr(email, "customer_email_brand_name", AsyncMock(return_value="Fixture"))
    monkeypatch.setattr(email, "_send", send_email)
    event = AutomationEvent(
        id=uuid.uuid4(), workspace_id=WORKSPACE_ID, contact_id=contact.id, payload={}
    )

    async def dispatch() -> None:
        if trigger_path == "event":
            await worker._execute_event_for_automation(automation, event, contact, db)
        else:
            await worker._execute_for_contact(automation, contact, db)

    with pytest.raises(SimulatedWorkerCrash):
        await dispatch()
    interrupted = db.add.call_args.args[0]
    await dispatch()
    completed = db.add.call_args.args[0]
    _assert_retry_steps(interrupted, completed, attempts, accepted)

    # A second event for the same contact is a legitimate new execution.
    # Polling intentionally allows only one execution per automation/contact.
    if trigger_path == "event":
        event.id = uuid.uuid4()
        await dispatch()
        assert db.add.call_args.args[0].id != completed.id
        assert len(accepted) == 4
        assert len(set(attempts[3:])) == 2

    # Completed actions cannot be replayed, even by direct action dispatch.
    await worker._run_actions(automation, contact, {}, completed, db)
    assert len(attempts) == (5 if trigger_path == "event" else 3)


@pytest.mark.parametrize("trigger_path", ["event", "poll"])
@pytest.mark.parametrize("status", ["completed", "pending", "failed"])
async def test_legacy_execution_is_not_replayed(trigger_path: str, status: str) -> None:
    """No safe legacy step checkpoint exists: never reset keys or resume rows."""
    from app.models.automation_event import AutomationEvent

    worker = AutomationWorker()
    automation = _automation([{"type": "send_sms", "config": {"message": "Hi"}}])
    legacy = _execution(automation)
    legacy.status = status
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=(legacy.id,))))
    db.flush = AsyncMock()
    with patch.object(worker, "_run_actions", AsyncMock()) as run:
        if trigger_path == "event":
            event = AutomationEvent(id=uuid.uuid4(), contact_id=42, payload={})
            await worker._execute_event_for_automation(automation, event, _contact(), db)
        else:
            await worker._execute_for_contact(automation, _contact(), db)
    run.assert_not_awaited()
    db.add.assert_not_called()
    assert legacy.status == status


async def test_polling_skips_incomplete_automation() -> None:
    """Incomplete automations never fan out to (and burn) matching contacts."""
    worker = AutomationWorker()
    automation = _automation([{"type": "send_sms", "config": {}}])

    with patch.object(worker, "_get_trigger_contacts", AsyncMock()) as get_contacts:
        await worker._evaluate_automation(automation, MagicMock())

    get_contacts.assert_not_awaited()
