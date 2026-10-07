"""Reminder provider-acceptance contract (RF-009).

``TelnyxSMSService.send_message`` returns a ``FAILED`` Message instead of
raising when the provider rejects a send. Manual and scheduled reminders must
only report "sent" / mark reminder flags when the provider accepted the
message, must surface a failure with a recovery path, and must never send a
second accepted message for the same reminder.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.conversation import MessageStatus
from app.services.calendar import reminder_service
from app.services.calendar.reminder_service import (
    MANUAL_REMINDER_MAX_ATTEMPTS,
    SCHEDULED_REMINDER_MAX_ATTEMPTS,
    is_provider_accepted,
    reminder_attempt_key,
    send_appointment_reminder,
)
from app.services.idempotency import derive_outbound_key
from app.workers.reminder_worker import ReminderWorker

SCHEDULED_AT = "2026-10-08T15:00:00+00:00"
FROM_NUMBER = "+12025556789"
TO_NUMBER = "+12025551234"

Outcome = str | Exception


class FakeProvider:
    """Mimics ``TelnyxSMSService.send_message`` idempotency + status contract.

    Messages are stored per idempotency key. An existing non-queued row is
    returned unchanged (the real service's ``text_send_idempotent_skip``).
    ``outcomes`` drives each fresh provider call: a status string or an
    exception raised before the provider responds.
    """

    def __init__(self, outcomes: list[Outcome]) -> None:
        self.outcomes = list(outcomes)
        self.store: dict[uuid.UUID, SimpleNamespace] = {}
        self.provider_calls: list[uuid.UUID] = []
        self.close = AsyncMock()

    async def find(self, _db: Any, key: uuid.UUID | None) -> SimpleNamespace | None:
        return self.store.get(key) if key else None

    async def send_message(self, *, idempotency_key: uuid.UUID, **_kw: Any) -> SimpleNamespace:
        existing = self.store.get(idempotency_key)
        if existing is not None and existing.status != MessageStatus.QUEUED:
            return existing
        self.provider_calls.append(idempotency_key)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        msg = existing or SimpleNamespace(id=uuid.uuid4())
        msg.status = outcome
        msg.error_message = "Invalid destination number" if outcome == "failed" else None
        self.store[idempotency_key] = msg
        return msg

    @property
    def accepted_count(self) -> int:
        return sum(1 for m in self.store.values() if is_provider_accepted(m))  # type: ignore[arg-type]


def _contact() -> SimpleNamespace:
    return SimpleNamespace(
        id=1, phone_number=TO_NUMBER, first_name="Ava", last_name="B", email="a@b.com"
    )


def _workspace() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), settings={"timezone": "UTC"})


# ---------------------------------------------------------------------------
# Shared rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "accepted"),
    [
        (MessageStatus.SENT, True),
        (MessageStatus.SENDING, True),
        (MessageStatus.DELIVERED, True),
        (MessageStatus.FAILED, False),
        (MessageStatus.QUEUED, False),
    ],
)
def test_is_provider_accepted(status: MessageStatus, accepted: bool) -> None:
    assert is_provider_accepted(SimpleNamespace(status=status)) is accepted  # type: ignore[arg-type]


def test_first_attempt_key_is_unchanged_and_retries_are_distinct() -> None:
    parts = ("manual_appointment_reminder", 7)
    keys = [reminder_attempt_key(parts, n) for n in range(3)]
    assert keys[0] == derive_outbound_key("manual_appointment_reminder", 7)
    assert len(set(keys)) == 3


# ---------------------------------------------------------------------------
# Manual reminders
# ---------------------------------------------------------------------------


class ManualHarness:
    def __init__(self, provider: FakeProvider) -> None:
        self.provider = provider
        self.appointment = SimpleNamespace(id=7, reminder_sent_at=None)
        self.db = MagicMock()
        self.db.execute = AsyncMock()
        self.db.commit = AsyncMock()

    async def send(self) -> dict[str, Any]:
        opt_out = MagicMock(check_opt_out=AsyncMock(return_value=False))
        with (
            patch.object(reminder_service, "settings", SimpleNamespace(telnyx_api_key="k")),
            patch.object(reminder_service, "_opt_out_manager", opt_out),
            patch.object(
                reminder_service, "resolve_from_number", AsyncMock(return_value=FROM_NUMBER)
            ),
            patch.object(reminder_service, "render_reminder_body", return_value="hi"),
            patch.object(reminder_service, "TelnyxSMSService", return_value=self.provider),
            patch.object(reminder_service, "find_message_by_idempotency_key", self.provider.find),
        ):
            return await send_appointment_reminder(
                db=self.db,
                appointment=self.appointment,  # type: ignore[arg-type]
                workspace=_workspace(),  # type: ignore[arg-type]
                contact=_contact(),  # type: ignore[arg-type]
                agent=None,
            )

    @property
    def flag_updates(self) -> int:
        return sum(
            1 for c in self.db.execute.await_args_list if "reminder_sent_at" in str(c.args[0])
        )


@pytest.mark.asyncio
async def test_manual_failed_message_is_not_reported_sent() -> None:
    h = ManualHarness(FakeProvider(["failed"]))

    result = await h.send()

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["retryable"] is True
    assert "Invalid destination number" in result["message"]
    assert result["sent_to"] is None
    assert h.appointment.reminder_sent_at is None
    assert h.flag_updates == 0


@pytest.mark.asyncio
async def test_manual_provider_acceptance_reports_sent_not_delivered() -> None:
    h = ManualHarness(FakeProvider(["sent"]))

    result = await h.send()

    assert result["success"] is True
    assert result["status"] == "sent"
    assert result["message"] == "Reminder sent"
    assert "deliver" not in result["message"].lower()
    assert result["sent_to"] == "***-***-1234"
    assert h.appointment.reminder_sent_at is not None
    assert h.flag_updates == 1


@pytest.mark.asyncio
async def test_manual_thrown_provider_error_propagates_without_flags() -> None:
    h = ManualHarness(FakeProvider([RuntimeError("telnyx down")]))

    with pytest.raises(RuntimeError, match="telnyx down"):
        await h.send()

    assert h.appointment.reminder_sent_at is None
    assert h.flag_updates == 0


@pytest.mark.asyncio
async def test_manual_retry_after_failure_sends_once_then_dedupes() -> None:
    provider = FakeProvider(["failed", "sent"])
    h = ManualHarness(provider)

    first = await h.send()
    second = await h.send()
    third = await h.send()

    assert first["success"] is False
    assert second["status"] == "sent"
    assert third["status"] == "already_sent"
    assert third["success"] is True
    # Retry used a fresh key (provider consumed the failed one); the repeat
    # press made no provider call and only one message was ever accepted.
    assert provider.provider_calls == [
        reminder_attempt_key(("manual_appointment_reminder", 7), 0),
        reminder_attempt_key(("manual_appointment_reminder", 7), 1),
    ]
    assert provider.accepted_count == 1
    assert h.flag_updates == 1


@pytest.mark.asyncio
async def test_manual_resumes_queued_attempt_with_same_key() -> None:
    provider = FakeProvider(["sent"])
    key0 = reminder_attempt_key(("manual_appointment_reminder", 7), 0)
    provider.store[key0] = SimpleNamespace(id=uuid.uuid4(), status=MessageStatus.QUEUED)
    h = ManualHarness(provider)

    result = await h.send()

    assert result["status"] == "sent"
    assert provider.provider_calls == [key0]


@pytest.mark.asyncio
async def test_manual_attempts_exhausted_stop_sending() -> None:
    provider = FakeProvider(["failed"] * MANUAL_REMINDER_MAX_ATTEMPTS)
    h = ManualHarness(provider)

    results = [await h.send() for _ in range(MANUAL_REMINDER_MAX_ATTEMPTS + 1)]

    assert [r["retryable"] for r in results[:-2]] == [True] * (MANUAL_REMINDER_MAX_ATTEMPTS - 1)
    assert results[-2]["retryable"] is False  # last allowed attempt failed
    final = results[-1]
    assert final == {
        "success": False,
        "status": "failed",
        "message": final["message"],
        "sent_to": None,
        "retryable": False,
    }
    assert "was not sent" in final["message"]
    assert len(provider.provider_calls) == MANUAL_REMINDER_MAX_ATTEMPTS
    assert h.flag_updates == 0


# ---------------------------------------------------------------------------
# Scheduled (worker) reminders
# ---------------------------------------------------------------------------


class WorkerHarness:
    def __init__(self, provider: FakeProvider) -> None:
        self.provider = provider
        self.worker = ReminderWorker()
        self.worker.opt_out_manager = MagicMock(check_opt_out=AsyncMock(return_value=False))
        self.mark = AsyncMock()
        self.dead_letter = AsyncMock()
        self.appt = SimpleNamespace(
            id=4242,
            agent=None,
            contact=_contact(),
            workspace=_workspace(),
            scheduled_at=SCHEDULED_AT,
            reminders_sent=[],
        )
        self.db = MagicMock()
        self.db.commit = AsyncMock()

    async def tick(self, offset: int = 60) -> None:
        from app.workers import reminder_worker

        with (
            patch.object(reminder_worker, "settings", SimpleNamespace(telnyx_api_key="k")),
            patch.object(
                reminder_worker, "resolve_from_number", AsyncMock(return_value=FROM_NUMBER)
            ),
            patch.object(reminder_worker, "TelnyxSMSService", return_value=self.provider),
            patch.object(reminder_service, "find_message_by_idempotency_key", self.provider.find),
            patch.object(self.worker, "_render_reminder_body", return_value="hi"),
            patch.object(self.worker, "_mark_offset_sent", self.mark),
            patch.object(self.worker, "_dead_letter", self.dead_letter),
        ):
            await self.worker._send_reminder(self.appt, offset, self.db)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_worker_failed_message_does_not_mark_offset() -> None:
    h = WorkerHarness(FakeProvider(["failed"]))

    await h.tick()

    h.mark.assert_not_awaited()
    h.dead_letter.assert_not_awaited()  # next tick retries


@pytest.mark.asyncio
async def test_worker_thrown_provider_error_does_not_mark_offset() -> None:
    h = WorkerHarness(FakeProvider([RuntimeError("timeout")]))

    await h.tick()

    h.mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_acceptance_marks_offset_once() -> None:
    provider = FakeProvider(["sent"])
    h = WorkerHarness(provider)

    await h.tick()
    # A repeat tick (e.g. the mark commit was lost) must not resend.
    await h.tick()

    assert provider.provider_calls == [
        derive_outbound_key("reminder", 4242, SCHEDULED_AT, 60),
    ]
    assert h.mark.await_count == 2
    assert provider.accepted_count == 1


@pytest.mark.asyncio
async def test_worker_repeated_failures_dead_letter_then_stop() -> None:
    provider = FakeProvider(["failed"] * SCHEDULED_REMINDER_MAX_ATTEMPTS)
    h = WorkerHarness(provider)

    for _ in range(SCHEDULED_REMINDER_MAX_ATTEMPTS + 2):
        await h.tick()

    assert len(provider.provider_calls) == SCHEDULED_REMINDER_MAX_ATTEMPTS
    h.mark.assert_not_awaited()
    h.dead_letter.assert_awaited_once()
    assert h.dead_letter.await_args.kwargs["item_key"] == "reminder:4242:offset:60"
    assert "rejected by provider" in str(h.dead_letter.await_args.args[3])


@pytest.mark.asyncio
async def test_worker_recovers_on_retry_after_failure() -> None:
    provider = FakeProvider(["failed", "sent"])
    h = WorkerHarness(provider)

    await h.tick()
    await h.tick()

    h.mark.assert_awaited_once()
    h.dead_letter.assert_not_awaited()
    assert provider.accepted_count == 1


@pytest.mark.asyncio
async def test_worker_opt_out_still_short_circuits_before_send() -> None:
    provider = FakeProvider([])
    h = WorkerHarness(provider)
    h.worker.opt_out_manager.check_opt_out = AsyncMock(return_value=True)

    await h.tick()

    assert provider.provider_calls == []
    h.mark.assert_awaited_once()


@pytest.mark.parametrize(
    ("outcome", "manual_success", "worker_marked"),
    [("failed", False, False), ("sent", True, True)],
)
@pytest.mark.asyncio
async def test_manual_and_worker_apply_same_rule(
    outcome: str, manual_success: bool, worker_marked: bool
) -> None:
    manual = ManualHarness(FakeProvider([outcome]))
    worker = WorkerHarness(FakeProvider([outcome]))

    result = await manual.send()
    await worker.tick()

    assert result["success"] is manual_success
    assert (manual.flag_updates == 1) is manual_success
    assert worker.mark.await_count == (1 if worker_marked else 0)
