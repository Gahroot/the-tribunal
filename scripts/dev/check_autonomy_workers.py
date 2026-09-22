#!/usr/bin/env python3
"""Autonomy-critical worker health check (script + assertions).

The Tribunal autonomously runs the entire prestyj Batch Video Ads sales
department over iMessage 24/7 — but that unattended loop only works if a
specific subset of background workers is both *registered* in
``start_all_workers()`` and actually *ticking*. This check proves exactly that
and surfaces a single PASS/FAIL plus the name of any silent worker.

It runs in two phases:

1. **Static registration** (in-process, no backend needed): asserts each
   autonomy-critical worker is present in ``WORKER_SPECS`` (so
   ``start_all_workers`` will start it) and is enabled under the current
   settings. A worker that's missing or gated off is reported here.

2. **Runtime liveness** (HTTP, against a locally started backend): GETs
   ``/readyz/autonomy`` on the running API and asserts each worker is running
   with a fresh Redis heartbeat — which a worker only writes at the end of a
   completed poll cycle (``BaseWorker._run_loop``). This proves the loops
   started cleanly and are emitting their poll/activity cycle.

Run from the backend directory so pydantic loads ``backend/.env``:

    cd backend && uv run python ../scripts/dev/check_autonomy_workers.py

Useful flags:

    --url http://localhost:8000   Backend base URL (default).
    --no-http                     Skip phase 2 (static registration only).
    --json                        Emit a machine-readable JSON summary instead
                                  of the human table.

Exits 0 when every autonomy-critical worker passes both phases, 1 otherwise.

Confirm the loops in the server log alongside this check:

    .ezcoder/eyes/logs.sh --service backend \\
      --grep "nudge_worker|experiment_evaluation|operator_report_worker|loop_completed|Traceback"
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx

from app.core.config import settings
from app.workers import WORKER_SPECS
from app.workers.autonomy_health import AUTONOMY_CRITICAL_WORKERS

_DEFAULT_URL = "http://localhost:8000"
_HTTP_TIMEOUT_SECONDS = 5.0


def _check_registration() -> tuple[bool, list[dict[str, Any]]]:
    """Phase 1: assert each critical worker is registered and enabled.

    Returns ``(ok, rows)`` where each row describes one worker's static state.
    """
    by_name = {spec.name: spec for spec in WORKER_SPECS}
    rows: list[dict[str, Any]] = []
    ok = True
    for name in AUTONOMY_CRITICAL_WORKERS:
        spec = by_name.get(name)
        registered = spec is not None
        enabled = bool(spec.is_enabled(settings)) if spec is not None else False
        reason = None
        if not registered:
            reason = "not registered in WORKER_SPECS"
        elif not enabled:
            reason = f"disabled ({spec.enabled_setting}=false)"
        worker_ok = registered and enabled
        ok = ok and worker_ok
        rows.append(
            {
                "name": name,
                "registered": registered,
                "enabled": enabled,
                "ok": worker_ok,
                "reason": reason,
            }
        )
    return ok, rows


def _check_runtime(url: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    """Phase 2: query ``/readyz/autonomy`` on the running backend.

    Returns ``(ok, body, error)``. ``error`` is set when the endpoint could
    not be reached or returned an unexpected payload.
    """
    endpoint = f"{url.rstrip('/')}/readyz/autonomy"
    try:
        resp = httpx.get(endpoint, timeout=_HTTP_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        return False, None, f"could not reach {endpoint}: {type(exc).__name__}: {exc}"

    try:
        body = resp.json()
    except ValueError:
        return False, None, f"non-JSON response from {endpoint} (status {resp.status_code})"

    # 200 ⇒ all critical workers ticking; 503 ⇒ at least one silent.
    return bool(body.get("ok")), body, None


def _print_table(reg_rows: list[dict[str, Any]], runtime_body: dict[str, Any] | None) -> None:
    """Render a human-readable per-worker table to stdout."""
    runtime_by_name: dict[str, dict[str, Any]] = {}
    if runtime_body is not None:
        for w in runtime_body.get("workers", []):
            runtime_by_name[w["name"]] = w

    header = (
        f"{'WORKER':<32} {'REGISTERED':<11} {'ENABLED':<8} "
        f"{'RUNNING':<8} {'TICKING':<8} STATUS"
    )
    print(header)
    print("-" * len(header))
    for row in reg_rows:
        name = row["name"]
        rt = runtime_by_name.get(name)
        running = "—"
        ticking = "—"
        if rt is not None:
            running = "yes" if rt.get("running") else "NO"
            ticking = "yes" if rt.get("heartbeat_present") else "NO"
        worker_ok = row["ok"] and (rt is None or bool(rt.get("ok")))
        status = "PASS" if worker_ok else "FAIL"
        reason = row["reason"] or (rt.get("reason") if rt else None)
        suffix = f"  ({reason})" if reason and not worker_ok else ""
        print(
            f"{name:<32} "
            f"{('yes' if row['registered'] else 'NO'):<11} "
            f"{('yes' if row['enabled'] else 'NO'):<8} "
            f"{running:<8} "
            f"{ticking:<8} "
            f"{status}{suffix}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomy-critical worker health check.")
    parser.add_argument("--url", default=_DEFAULT_URL, help="Backend base URL.")
    parser.add_argument(
        "--no-http",
        action="store_true",
        help="Skip the runtime HTTP phase (static registration check only).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    args = parser.parse_args()

    reg_ok, reg_rows = _check_registration()

    runtime_ok = True
    runtime_body: dict[str, Any] | None = None
    runtime_error: str | None = None
    if not args.no_http:
        runtime_ok, runtime_body, runtime_error = _check_runtime(args.url)

    overall_ok = reg_ok and (args.no_http or (runtime_ok and runtime_error is None))

    # Determine silent workers (fail either phase).
    silent: list[str] = [r["name"] for r in reg_rows if not r["ok"]]
    if runtime_body is not None:
        silent.extend(s for s in runtime_body.get("silent", []) if s not in silent)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": overall_ok,
                    "silent": silent,
                    "registration": reg_rows,
                    "runtime": runtime_body,
                    "runtime_error": runtime_error,
                },
                indent=2,
            )
        )
    else:
        print("== Autonomy-critical worker health ==\n")
        _print_table(reg_rows, runtime_body)
        print()
        if runtime_error:
            print(f"⚠ runtime check skipped/failed: {runtime_error}")
        if overall_ok:
            print("RESULT: PASS — every autonomy-critical worker is registered and ticking.")
        else:
            print(f"RESULT: FAIL — silent worker(s): {', '.join(silent) or 'unknown'}")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
