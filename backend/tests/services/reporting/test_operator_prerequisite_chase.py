"""Unit tests for the operator-report setup-prerequisite chase.

These exercise the anti-spam re-chase logic without a database by stubbing the
prerequisite evaluation and the delivery rail, so the focus stays on *when* the
chase fires and *what* it says.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.services.dashboard.setup_prerequisites import (
    SetupPrerequisite,
    SetupPrerequisiteReport,
)
from app.services.reporting.operator_report_service import (
    _CHASE_STATE_KEY,
    OperatorReportService,
)

pytestmark = pytest.mark.asyncio


class _FakeDB:
    async def commit(self) -> None:  # pragma: no cover - trivial
        return None


class _FakeWorkspace:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.name = "Prestyj"
        self.settings: dict = {}


class _FakePhone:
    phone_number = "+18885550197"


def _prereq(key: str, gap: str, *, met: bool) -> SetupPrerequisite:
    return SetupPrerequisite(
        key=key,
        gap=gap,
        met=met,
        short_title=f"{key} thing",
        title=f"{key} title",
        body=f"{key} body",
        fix=f"Do the {key} fix.",
        cta_label="Go",
        href=f"/{key}",
    )


def _report(*specs: tuple[str, str, bool]) -> SetupPrerequisiteReport:
    return SetupPrerequisiteReport(
        prerequisites=tuple(_prereq(k, g, met=m) for k, g, m in specs)
    )


def _patch_report(monkeypatch: pytest.MonkeyPatch, report: SetupPrerequisiteReport) -> None:
    async def _evaluate(self, workspace_id):  # noqa: ANN001
        return report

    monkeypatch.setattr(
        "app.services.dashboard.setup_prerequisites.SetupPrerequisiteService.evaluate",
        _evaluate,
    )


def _capture_delivery(monkeypatch: pytest.MonkeyPatch, sink: list[str]) -> None:
    async def _deliver(self, db, workspace, recipient, phone, body, *, scope, parts):  # noqa: ANN001
        sink.append(body)
        return True

    monkeypatch.setattr(OperatorReportService, "_deliver", _deliver)


async def _chase(service, db, ws, now):  # noqa: ANN001
    return await service._maybe_prerequisite_chase(db, ws, "+14155551997", _FakePhone(), now)


async def test_chase_lists_blocked_prereqs_with_fixes(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    _capture_delivery(monkeypatch, sent)
    _patch_report(
        monkeypatch,
        _report(
            ("monitor", "monitor", True),
            ("offer", "offer", True),
            ("autopilot", "autopilot", True),
            ("delivery", "telephony", True),
            ("extra", "extra", False),
            ("two", "two", False),
        ),
    )
    ws = _FakeWorkspace()
    now = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)

    result = await _chase(OperatorReportService(), _FakeDB(), ws, now)

    assert result == "prerequisite_chase"
    assert len(sent) == 1
    body = sent[0]
    assert "4 of 6 prerequisites" in body
    assert "Do the extra fix." in body
    assert "Do the two fix." in body
    assert ws.settings[_CHASE_STATE_KEY]["unmet_signature"] == "extra,two"


async def test_chase_not_repeated_same_day_same_gaps(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    _capture_delivery(monkeypatch, sent)
    _patch_report(monkeypatch, _report(("offer", "offer", False)))
    ws = _FakeWorkspace()
    now = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
    service = OperatorReportService()

    first = await _chase(service, _FakeDB(), ws, now)
    second = await _chase(service, _FakeDB(), ws, now.replace(hour=11))

    assert first == "prerequisite_chase"
    assert second is None
    assert len(sent) == 1


async def test_chase_refires_when_gap_set_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    _capture_delivery(monkeypatch, sent)
    ws = _FakeWorkspace()
    now = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
    service = OperatorReportService()

    _patch_report(monkeypatch, _report(("offer", "offer", False), ("monitor", "monitor", False)))
    await _chase(service, _FakeDB(), ws, now)

    # Operator resolved the monitor gap → unmet set shrank → re-chase same day.
    _patch_report(monkeypatch, _report(("offer", "offer", False), ("monitor", "monitor", True)))
    again = await _chase(service, _FakeDB(), ws, now.replace(hour=10))

    assert again == "prerequisite_chase"
    assert len(sent) == 2


async def test_chase_refires_next_day(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    _capture_delivery(monkeypatch, sent)
    _patch_report(monkeypatch, _report(("offer", "offer", False)))
    ws = _FakeWorkspace()
    service = OperatorReportService()

    await _chase(service, _FakeDB(), ws, datetime(2026, 6, 15, 9, 0, tzinfo=UTC))
    again = await _chase(service, _FakeDB(), ws, datetime(2026, 6, 16, 9, 0, tzinfo=UTC))

    assert again == "prerequisite_chase"
    assert len(sent) == 2


async def test_no_chase_and_state_cleared_when_all_met(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    _capture_delivery(monkeypatch, sent)
    ws = _FakeWorkspace()
    ws.settings[_CHASE_STATE_KEY] = {"unmet_signature": "offer", "last_chased_date": "2026-06-15"}
    _patch_report(monkeypatch, _report(("offer", "offer", True)))
    now = datetime(2026, 6, 16, 9, 0, tzinfo=UTC)

    result = await _chase(OperatorReportService(), _FakeDB(), ws, now)

    assert result is None
    assert not sent
    assert _CHASE_STATE_KEY not in ws.settings
