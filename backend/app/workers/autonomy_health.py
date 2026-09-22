"""Autonomy-critical worker health check.

The Tribunal's sales loop only runs unattended if a specific subset of
background workers is actually registered in :func:`start_all_workers` *and*
ticking. This module defines that canonical subset and a single check that
proves, for each one:

* **registered** — present in ``WORKER_SPECS`` (so ``start_all_workers`` will
  start it);
* **enabled** — its per-spec enablement predicate is true for the current
  settings (a disabled autonomy worker is a silent loop, not "fine");
* **running** — its registry has produced a live, ``running`` instance;
* **ticking** — its Redis heartbeat key is fresh, which a worker only writes
  at the end of each completed poll cycle (see ``BaseWorker._run_loop``). The
  stored value is the unix timestamp of the last completed cycle, so we can
  also surface heartbeat *age* and flag a wedged loop.

The result feeds both the ``/readyz/autonomy`` endpoint and the
``scripts/ops/check_autonomy_workers.py`` CLI so operators get one clear
pass/fail and the name of any silent worker.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import structlog

from app.core.config import Settings, settings
from app.db.redis import get_redis
from app.workers import WORKER_SPECS, WorkerSpec
from app.workers.base import HEARTBEAT_TTL_MULTIPLIER, heartbeat_key

logger = structlog.get_logger()

# Canonical autonomy-critical workers, keyed by their heartbeat
# ``component_name`` (which equals the ``WorkerSpec.name`` for each). Keep this
# list in lockstep with the sales-loop responsibilities documented per entry.
AUTONOMY_CRITICAL_WORKERS: tuple[str, ...] = (
    # First-touch outbound drafts — opens the conversation with new leads.
    "outbound_auto_draft_worker",
    # Variant fan-out: sends competing message variants under test.
    "message_test_worker",
    # Variant winners: evaluates experiments and promotes the winning copy.
    "experiment_evaluation",
    # Human-in-the-loop nudge generation + delivery to operators.
    "nudge_worker",
    # Proactive operator reporting over iMessage (the reporting worker).
    "operator_report_worker",
)

# Budget for the Redis round-trip that reads heartbeat keys.
_PROBE_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class AutonomyWorkerStatus:
    """Per-worker health snapshot for an autonomy-critical worker."""

    name: str
    registered: bool
    enabled: bool
    running: bool
    heartbeat_present: bool
    ok: bool
    reason: str | None = None
    heartbeat_age_seconds: int | None = None
    poll_interval_seconds: int | None = None
    max_heartbeat_age_seconds: int | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view for the health endpoint."""
        return {
            "name": self.name,
            "registered": self.registered,
            "enabled": self.enabled,
            "running": self.running,
            "heartbeat_present": self.heartbeat_present,
            "ok": self.ok,
            "reason": self.reason,
            "heartbeat_age_seconds": self.heartbeat_age_seconds,
            "poll_interval_seconds": self.poll_interval_seconds,
            "max_heartbeat_age_seconds": self.max_heartbeat_age_seconds,
        }


@dataclass(frozen=True, slots=True)
class AutonomyHealthReport:
    """Aggregate health for the autonomy-critical worker set."""

    ok: bool
    workers: list[AutonomyWorkerStatus] = field(default_factory=list)
    error: str | None = None

    @property
    def silent(self) -> list[str]:
        """Names of autonomy-critical workers that are not healthy."""
        return [w.name for w in self.workers if not w.ok]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view for the health endpoint."""
        return {
            "ok": self.ok,
            "error": self.error,
            "silent": self.silent,
            "workers": [w.as_dict() for w in self.workers],
        }


def _spec_by_name() -> dict[str, WorkerSpec]:
    """Index ``WORKER_SPECS`` by spec name for O(1) lookup."""
    return {spec.name: spec for spec in WORKER_SPECS}


async def _read_heartbeats(labels: list[str]) -> tuple[dict[str, int | None], str | None]:
    """Return ``(label -> last-cycle-unix-ts | None, error)`` via one MGET.

    A single ``MGET`` borrows at most one connection from the bounded Redis
    pool regardless of how many labels we read, mirroring the ``/readyz``
    heartbeat probe. A ``None`` value means the key is missing/expired.
    """
    if not labels:
        return {}, None
    try:

        async def _run() -> dict[str, int | None]:
            client = await get_redis()
            values = await client.mget([heartbeat_key(label) for label in labels])
            out: dict[str, int | None] = {}
            for label, raw in zip(labels, values, strict=True):
                if raw is None:
                    out[label] = None
                    continue
                try:
                    out[label] = int(raw)
                except (TypeError, ValueError):
                    out[label] = None
            return out

        return await asyncio.wait_for(_run(), timeout=_PROBE_TIMEOUT_SECONDS), None
    except TimeoutError:
        return dict.fromkeys(labels, None), "timeout"
    except Exception as exc:  # noqa: BLE001 — surface any driver/connection error
        return dict.fromkeys(labels, None), type(exc).__name__


async def check_autonomy_workers(
    runtime_settings: Settings | None = None,
    *,
    critical: tuple[str, ...] = AUTONOMY_CRITICAL_WORKERS,
) -> AutonomyHealthReport:
    """Check that every autonomy-critical worker is registered and ticking.

    Args:
        runtime_settings: Settings used to evaluate per-spec enablement.
            Defaults to the process settings.
        critical: Override the set of worker names to verify (tests).

    Returns:
        An :class:`AutonomyHealthReport` with one entry per critical worker.
    """
    resolved = runtime_settings or settings
    specs = _spec_by_name()

    # Read heartbeats for every critical worker that is registered, in one trip.
    candidate_labels = [name for name in critical if name in specs]
    heartbeats, redis_error = await _read_heartbeats(candidate_labels)
    now = int(time.time())

    statuses: list[AutonomyWorkerStatus] = []
    for name in critical:
        spec = specs.get(name)
        if spec is None:
            statuses.append(
                AutonomyWorkerStatus(
                    name=name,
                    registered=False,
                    enabled=False,
                    running=False,
                    heartbeat_present=False,
                    ok=False,
                    reason="not_registered",
                )
            )
            continue

        enabled = bool(spec.is_enabled(resolved))
        instance = spec.registry.get()
        running = bool(instance is not None and getattr(instance, "running", False))
        poll_interval = (
            int(instance._poll_interval)  # noqa: SLF001 — own subclass surface
            if instance is not None
            else None
        )
        max_age = poll_interval * HEARTBEAT_TTL_MULTIPLIER if poll_interval is not None else None

        ts = heartbeats.get(name)
        heartbeat_present = ts is not None
        age = (now - ts) if ts is not None else None

        reason: str | None = None
        if not enabled:
            reason = "disabled"
        elif not running:
            reason = "not_running"
        elif redis_error is not None:
            reason = f"redis_error:{redis_error}"
        elif not heartbeat_present:
            reason = "no_heartbeat"

        ok = enabled and running and heartbeat_present and redis_error is None

        statuses.append(
            AutonomyWorkerStatus(
                name=name,
                registered=True,
                enabled=enabled,
                running=running,
                heartbeat_present=heartbeat_present,
                ok=ok,
                reason=reason,
                heartbeat_age_seconds=age,
                poll_interval_seconds=poll_interval,
                max_heartbeat_age_seconds=max_age,
            )
        )

    overall_ok = all(s.ok for s in statuses)
    report = AutonomyHealthReport(ok=overall_ok, workers=statuses, error=redis_error)
    if not overall_ok:
        logger.warning(
            "autonomy_workers_unhealthy",
            silent=report.silent,
            redis_error=redis_error,
        )
    return report


__all__ = [
    "AUTONOMY_CRITICAL_WORKERS",
    "AutonomyHealthReport",
    "AutonomyWorkerStatus",
    "check_autonomy_workers",
]
