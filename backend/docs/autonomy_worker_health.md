# Autonomy-critical worker health check

The Tribunal runs the Prestyj Batch Video Ads sales department autonomously over
iMessage 24/7. That unattended loop only works if a specific subset of
background workers is **both** registered in `start_all_workers()` **and**
actually ticking. If one of them goes silent, leads stop getting first-touched,
winning message variants stop shipping, nudges stop reaching operators, or the
operator stops getting proactive reports — quietly, with no error.

This check is the repeatable "is the autonomy loop alive?" proof for that worker
set. It surfaces a single PASS/FAIL plus the name of any silent worker.

## The autonomy-critical workers

Defined canonically in `backend/app/workers/autonomy_health.py`
(`AUTONOMY_CRITICAL_WORKERS`), keyed by each worker's heartbeat
`COMPONENT_NAME`:

| Worker (`COMPONENT_NAME`)      | Sales-loop responsibility                          |
| ------------------------------ | -------------------------------------------------- |
| `outbound_auto_draft_worker`   | First-touch outbound drafts to new leads           |
| `message_test_worker`          | Sends competing message variants under test        |
| `experiment_evaluation`        | Evaluates experiments, promotes the winning copy   |
| `nudge_worker`                 | Generates + delivers human-in-the-loop nudges      |
| `operator_report_worker`       | Proactive operator reporting over iMessage         |

## What it asserts

For each autonomy-critical worker, two phases:

1. **Static registration** (in-process, no backend needed):
   - **registered** — present in `WORKER_SPECS`, so `start_all_workers()` will
     start it.
   - **enabled** — its per-spec enablement predicate is true for the current
     settings (a disabled autonomy worker is a silent loop, not "fine").
2. **Runtime liveness** (HTTP, against a locally started backend):
   - **running** — its registry has produced a live, `running` instance.
   - **ticking** — its Redis heartbeat key is fresh. A worker writes its
     heartbeat only at the **end** of a completed poll cycle
     (`BaseWorker._run_loop`), so a fresh key proves the loop is emitting its
     `loop_completed` poll/activity log. The stored value is the unix timestamp
     of the last completed cycle, so the report also surfaces heartbeat **age**
     and the worker's poll interval.

Pass = registered AND enabled AND running AND ticking, for every worker.

## Pieces

- `backend/app/workers/autonomy_health.py` — canonical worker set +
  `check_autonomy_workers()` (one MGET reads all heartbeats; mirrors the
  `/readyz` probe's bounded Redis usage).
- `GET /readyz/autonomy` (`backend/app/api/v1/health.py`) — focused readiness
  endpoint. Returns `200` when all critical workers tick, `503` with `silent`
  naming any worker that is missing / disabled / not running / wedged.
- `scripts/dev/check_autonomy_workers.py` — CLI that runs the static phase
  in-process and the runtime phase over HTTP, prints a per-worker table, and
  exits non-zero on failure.
- Tests: `backend/tests/workers/test_autonomy_health.py` and the
  `TestReadyzAutonomy` cases in `backend/tests/api/test_health.py`.

## How to run it

### 1. Start the backend with workers enabled

```bash
cd backend && RUN_BACKGROUND_WORKERS=true \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8010
```

(Postgres + Redis come from `backend/docker-compose.yml` / `make dev.db`.) The
workers can also run as the separate `uv run backend-workers` process; the
heartbeats land in the same Redis either way.

### 2. Run the check

```bash
cd backend && uv run python ../scripts/dev/check_autonomy_workers.py --url http://localhost:8010
```

Example PASS output:

```
WORKER                           REGISTERED  ENABLED  RUNNING  TICKING  STATUS
------------------------------------------------------------------------------
outbound_auto_draft_worker       yes         yes      yes      yes      PASS
message_test_worker              yes         yes      yes      yes      PASS
experiment_evaluation            yes         yes      yes      yes      PASS
nudge_worker                     yes         yes      yes      yes      PASS
operator_report_worker           yes         yes      yes      yes      PASS

RESULT: PASS — every autonomy-critical worker is registered and ticking.
```

Flags:

- `--no-http` — static registration check only (no running backend required).
- `--json` — machine-readable summary for CI/alerting.

You can also hit the endpoint directly:

```bash
.ezcoder/eyes/http.sh http://localhost:8010/readyz/autonomy
# or
curl -s http://localhost:8010/readyz/autonomy | python3 -m json.tool
```

### 3. Confirm the loops in the server log

The check proves heartbeats; the log proves the cycles. Start the backend so
its stdout/stderr lands in `.ezcoder/eyes/out/backend.log`, then:

```bash
# Each autonomy-critical worker should have >=1 completed cycle:
for w in outbound_auto_draft_worker message_test_worker experiment_evaluation \
         nudge_worker operator_report_worker; do
  printf "%s: " "$w"
  grep -cE "loop_completed.*worker=$w" .ezcoder/eyes/out/backend.log
done

# No worker-loop errors for the critical set:
grep -oE "Error in worker loop +component=[a-z_]+" .ezcoder/eyes/out/backend.log | sort | uniq -c
```

`.ezcoder/eyes/logs.sh --file .ezcoder/eyes/out/backend.log --grep "loop_completed"`
works too. (When `--service backend` resolves to the wrong root, pass `--file`
with the explicit repo-local log path.)

## Notes

- `GET /readyz/autonomy` is a health probe and is **not** consumed by the typed
  frontend client. Adding it does require `make codegen` to refresh
  `backend/openapi.json` + `frontend/src/lib/api/_generated.ts`; run that
  separately so it doesn't sweep up any unrelated in-flight OpenAPI drift.
- This is narrower than `/readyz`, which checks *every* worker's heartbeat plus
  Postgres/Redis. Use `/readyz/autonomy` to alert specifically on the sales
  loop and to name the silent worker fast.
