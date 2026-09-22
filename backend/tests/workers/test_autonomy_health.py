"""Tests for the autonomy-critical worker health check."""

from __future__ import annotations

import time
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from app.workers import WORKER_SPECS
from app.workers import autonomy_health as ah
from app.workers.autonomy_health import (
    AUTONOMY_CRITICAL_WORKERS,
    check_autonomy_workers,
)


def test_critical_workers_are_all_registered_in_worker_specs() -> None:
    """Every autonomy-critical worker must be wired into start_all_workers()."""
    spec_names = {spec.name for spec in WORKER_SPECS}
    missing = [name for name in AUTONOMY_CRITICAL_WORKERS if name not in spec_names]
    assert missing == [], f"autonomy-critical workers missing from WORKER_SPECS: {missing}"


def test_critical_set_covers_the_documented_loop() -> None:
    """The canonical set matches the documented sales-loop responsibilities."""
    assert set(AUTONOMY_CRITICAL_WORKERS) == {
        "outbound_auto_draft_worker",
        "message_test_worker",
        "experiment_evaluation",
        "nudge_worker",
        "operator_report_worker",
    }


class _FakeInstance:
    def __init__(self, *, running: bool = True, poll_interval: int = 60) -> None:
        self.running = running
        self._poll_interval = poll_interval


class _FakeSpec:
    def __init__(self, name: str, *, enabled: bool, instance: object | None) -> None:
        self.name = name
        self.enabled_setting = "always"
        self._enabled = enabled
        self._instance = instance
        self.registry = self

    def is_enabled(self, _settings: object) -> bool:
        return self._enabled

    def get(self) -> object | None:
        return self._instance


@contextmanager
def _patch_env(specs: list[_FakeSpec], client: AsyncMock):
    """Patch both ``WORKER_SPECS`` and the Redis client for a check."""
    with (
        patch.object(ah, "WORKER_SPECS", tuple(specs)),
        patch.object(ah, "get_redis", new=AsyncMock(return_value=client)),
    ):
        yield


async def test_all_healthy_passes() -> None:
    """All critical workers registered, enabled, running, with fresh heartbeats."""
    names = list(AUTONOMY_CRITICAL_WORKERS)
    specs = [_FakeSpec(n, enabled=True, instance=_FakeInstance()) for n in names]
    now = str(int(time.time()))

    fake_client = AsyncMock()
    fake_client.mget = AsyncMock(return_value=[now] * len(names))

    with _patch_env(specs, fake_client):
        report = await check_autonomy_workers()

    assert report.ok is True
    assert report.silent == []
    assert all(w.ok for w in report.workers)
    assert {w.name for w in report.workers} == set(names)


async def test_missing_registration_flags_not_registered() -> None:
    """A critical worker absent from WORKER_SPECS is reported, not crashed on."""
    names = list(AUTONOMY_CRITICAL_WORKERS)
    # Drop the first critical worker from the registry entirely.
    specs = [_FakeSpec(n, enabled=True, instance=_FakeInstance()) for n in names[1:]]
    now = str(int(time.time()))

    fake_client = AsyncMock()
    fake_client.mget = AsyncMock(return_value=[now] * (len(names) - 1))

    with _patch_env(specs, fake_client):
        report = await check_autonomy_workers()

    assert report.ok is False
    dropped = names[0]
    status = next(w for w in report.workers if w.name == dropped)
    assert status.registered is False
    assert status.reason == "not_registered"
    assert dropped in report.silent


async def test_disabled_worker_is_silent() -> None:
    """A registered-but-disabled critical worker is treated as silent."""
    names = list(AUTONOMY_CRITICAL_WORKERS)
    specs = [_FakeSpec(n, enabled=True, instance=_FakeInstance()) for n in names]
    specs[0]._enabled = False
    now = str(int(time.time()))

    fake_client = AsyncMock()
    fake_client.mget = AsyncMock(return_value=[now] * len(names))

    with _patch_env(specs, fake_client):
        report = await check_autonomy_workers()

    assert report.ok is False
    status = next(w for w in report.workers if w.name == names[0])
    assert status.enabled is False
    assert status.reason == "disabled"


async def test_missing_heartbeat_flags_silent_worker() -> None:
    """A running worker with no heartbeat key is wedged ⇒ silent."""
    names = list(AUTONOMY_CRITICAL_WORKERS)
    specs = [_FakeSpec(n, enabled=True, instance=_FakeInstance()) for n in names]
    now = str(int(time.time()))
    # Second worker's heartbeat is missing (None).
    values: list[str | None] = [now] * len(names)
    values[1] = None

    fake_client = AsyncMock()
    fake_client.mget = AsyncMock(return_value=values)

    with _patch_env(specs, fake_client):
        report = await check_autonomy_workers()

    assert report.ok is False
    status = next(w for w in report.workers if w.name == names[1])
    assert status.heartbeat_present is False
    assert status.reason == "no_heartbeat"
    assert names[1] in report.silent


async def test_not_running_worker_is_silent() -> None:
    """A registered+enabled worker without a live instance is silent."""
    names = list(AUTONOMY_CRITICAL_WORKERS)
    specs = [_FakeSpec(n, enabled=True, instance=_FakeInstance()) for n in names]
    specs[2]._instance = None
    now = str(int(time.time()))

    fake_client = AsyncMock()
    fake_client.mget = AsyncMock(return_value=[now] * len(names))

    with _patch_env(specs, fake_client):
        report = await check_autonomy_workers()

    assert report.ok is False
    status = next(w for w in report.workers if w.name == names[2])
    assert status.running is False
    assert status.reason == "not_running"


async def test_redis_error_marks_workers_silent() -> None:
    """A Redis failure surfaces the error and fails the report."""
    names = list(AUTONOMY_CRITICAL_WORKERS)
    specs = [_FakeSpec(n, enabled=True, instance=_FakeInstance()) for n in names]

    class FakeConnError(Exception):
        pass

    fake_client = AsyncMock()
    fake_client.mget = AsyncMock(side_effect=FakeConnError("pool exhausted"))

    with _patch_env(specs, fake_client):
        report = await check_autonomy_workers()

    assert report.ok is False
    assert report.error == "FakeConnError"
    assert set(report.silent) == set(names)


async def test_heartbeat_age_is_computed() -> None:
    """A present heartbeat yields a non-negative age and poll metadata."""
    names = list(AUTONOMY_CRITICAL_WORKERS)
    specs = [_FakeSpec(n, enabled=True, instance=_FakeInstance(poll_interval=3600)) for n in names]
    past = str(int(time.time()) - 30)

    fake_client = AsyncMock()
    fake_client.mget = AsyncMock(return_value=[past] * len(names))

    with _patch_env(specs, fake_client):
        report = await check_autonomy_workers()

    assert report.ok is True
    sample = report.workers[0]
    assert sample.heartbeat_age_seconds is not None and sample.heartbeat_age_seconds >= 30
    assert sample.poll_interval_seconds == 3600
    assert sample.max_heartbeat_age_seconds == 3600 * 3
