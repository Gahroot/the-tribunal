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
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.automations import _to_response
from app.models.automation import Automation
from app.models.automation_execution import AutomationExecution
from app.workers.automation_worker import AutomationWorker

WORKSPACE_ID = uuid.uuid4()
FROM_NUMBER = "+15550001111"


class FakeTextProvider:
    """Captures sends instead of hitting Telnyx."""

    def __init__(self, status: str = "sent", error: str | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self._status = status
        self._error = error

    async def send_message(self, **kwargs: Any) -> SimpleNamespace:
        self.sent.append(kwargs)
        return SimpleNamespace(
            id=uuid.uuid4(),
            status=self._status,
            provider_message_id="fake-1",
            error_message=self._error,
        )

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
            "did not accept the message (carrier rejected)",
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


async def test_polling_skips_incomplete_automation() -> None:
    """Incomplete automations never fan out to (and burn) matching contacts."""
    worker = AutomationWorker()
    automation = _automation([{"type": "send_sms", "config": {}}])

    with patch.object(worker, "_get_trigger_contacts", AsyncMock()) as get_contacts:
        await worker._evaluate_automation(automation, MagicMock())

    get_contacts.assert_not_awaited()
