---
id: automations
name: Automations (Event Bus & Rules Engine)
tier: C
status: manifest
summary: The workspace automation engine — an internal event bus (events.py) other blocks emit to, plus a trigger/condition/action rules engine that drains those events and runs operator-defined automations (send message, place call, tag, escalate) in the background.
owns_paths:
  - backend/app/services/automations/
  - backend/app/api/v1/automations.py
  - backend/app/workers/automation_worker.py
  - backend/app/models/automation.py
  - backend/app/models/automation_event.py
  - backend/app/models/automation_execution.py
public_api:
  - backend/app/api/v1/automations.py::router
  - backend/app/services/automations/events.py::emit_automation_event
  - backend/app/services/automations/events.py::EVENT_MISSED_CALL
  - backend/app/services/automations/events.py::EVENT_ROLEPLAY_COMPLETED
  - backend/app/services/automations/events.py::EVENT_KNOWLEDGE_DOCUMENT_UPLOADED
depends_on: [core, contacts, hitl, voice]
external_integrations: []
env_vars: []
db_tables:
  - backend/app/models/automation.py::automations
  - backend/app/models/automation_event.py::automation_events
  - backend/app/models/automation_execution.py::automation_executions
alembic_migrations: shared linear chain — automations (add_automations_001_add_automations_table), automation_events (20260612_automation_events), automation_executions (shared automation infrastructure revisions in backend/alembic/versions/).
workers:
  - backend/app/workers/automation_worker.py
extraction_effort: medium
extraction_notes: The event-emit half (events.py::emit_automation_event) is a clean, core-adjacent seam many blocks already use to stay decoupled — that part travels easily. The hazard is the draining half: automation_worker executes actions by importing voice (telnyx_voice, text_provider), contacts (TagService), and hitl (approval_gate_service), so the worker, not the bus, carries the entanglement.
---

## Overview

Automations is the workspace rules engine. It has two halves that should not be confused. First, the **event bus** (`services/automations/events.py`): `emit_automation_event(db, workspace_id=..., event_type=..., ...)` plus the `EVENT_*` constants. Other blocks emit domain events here (a missed call, a completed roleplay, an uploaded knowledge doc, a received review) instead of importing each other's workers — this is the sanctioned decoupling seam documented in `BLOCK_SCHEMA.md`. Second, the **rules engine**: operator-defined automations (`automations` table) with triggers, conditions, and actions, persisted events (`automation_events`), and an execution ledger (`automation_executions`). The `automation_worker` drains pending events, matches them against each workspace's automations, and runs the resulting actions — send a message, place a call, tag a contact, or escalate to a human.

## Internal Dependencies

Sideways block imports to sever (non-`core`, from `docs/blocks/coupling-report.json`). All live in the **worker**, not the event bus:

- `backend/app/workers/automation_worker.py:73,74: from app.services.telephony.telnyx_voice import TelnyxVoiceService` / `text_provider import get_text_message_provider` → **voice** — automation actions that place calls or send SMS.
- `backend/app/workers/automation_worker.py:72: from app.services.tags import TagService` → **contacts** — automation actions that add/remove tags.
- `backend/app/workers/automation_worker.py:68: from app.services.approval.approval_gate_service import approval_gate_service` → **hitl** — automation actions that escalate to the approval queue.
- `backend/app/workers/automation_worker.py:75,76: from app.workers.base import BaseWorker, WorkerRegistry` / `retryable import RetryableWorker` → **core** — worker base.

The event bus (`events.py`) imports only `core` — it is intentionally a leaf so any block can emit without dragging in the engine.

Core: `app.api.deps` (`DB`, `CurrentUser`, `get_workspace`), `app.db.scope.apply_workspace_scope`, `app.db.pagination.paginate`, `app.db.session.AsyncSessionLocal`, `app.core.config.settings`, `app.services.idempotency.derive_outbound_key`/`derive_worker_retry_key`.

## Public Surface

- Authenticated REST routes: `/api/v1/workspaces/{workspace_id}/automations` (`automations.router`) — CRUD for operator-defined automations.
- The event bus: `emit_automation_event(...)` and the `EVENT_*` constants (`EVENT_MISSED_CALL` from voice, `EVENT_ROLEPLAY_COMPLETED` from agent-brain, `EVENT_KNOWLEDGE_DOCUMENT_UPLOADED` from knowledge, plus review/contact lifecycle events). This is the most widely imported symbol in the block and is the recommended way for any block to trigger automations.
- No exported frontend tree of its own in this block's scope.

## How to Extract

1. Pull `core` plus `contacts`, `hitl`, and `voice` transitively (needed only by the worker's action executors). The event bus alone needs nothing beyond core.
2. Copy `owns_paths` (automations service incl. `events.py`, the router, the worker, three model files).
3. Decide the extraction granularity: if you only need the **emit** seam in the new project, copy `events.py` + the three models and leave a no-op drain. To run automations, sever the worker's voice/contacts/hitl imports by injecting action-executor ports (an SMS/call port, a tagging port, an escalation port).
4. Mount the `automations` router; export `emit_automation_event` and the `EVENT_*` constants for emitting blocks.
5. No block-specific env vars (poll interval is internal); rely on core boot vars.
6. Port the three tables and their creating revisions.
7. Register `automation_worker` in the new runner gated on `RUN_BACKGROUND_WORKERS`.

## Risks

- **Bus vs. engine confusion:** copying `events.py` is cheap and lets other blocks compile; copying the *worker* is where the real coupling lives. Be explicit about which half a given extraction needs.
- **Silent no-op drains:** if a block emits events but the automation engine isn't pulled, rows accumulate in `automation_events` and never execute — correct behavior, but easy to mistake for a bug.
- **Action-executor breadth:** the worker can call, text, tag, and escalate; an incomplete executor port means some automation action types fail at runtime rather than at import time.
- **Polling fan-out:** `automation_worker` is an in-process poll loop; multiple replicas multiply draining unless workers are split out (see CLAUDE.md worker note).
- **Idempotency:** action execution derives idempotency keys via core; preserve `derive_outbound_key`/`derive_worker_retry_key` usage so retried events don't double-send.
