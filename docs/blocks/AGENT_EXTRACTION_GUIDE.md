# Agent Extraction Guide

How an AI agent pulls a **block** out of The Tribunal into a new project.

You will be told something like *"pull block X into a new project."* Your job is
to read the block's manifest, resolve everything it transitively needs, copy the
right files, and rewire them so the capability runs standalone. Do not read the
whole repo — the `BLOCK.md` manifests are the index.

Read `BLOCK_SCHEMA.md` first if you have not. Every block folder has a `BLOCK.md`
with strict YAML frontmatter plus prose sections.

---

## Procedure

### 1. Read the target block's `BLOCK.md`

Parse the YAML frontmatter. You now have `id`, `owns_paths`, `public_api`,
`depends_on`, `external_integrations`, `env_vars`, `db_tables`,
`alembic_migrations`, `workers`, `extraction_effort`, and `extraction_notes`.
Read the prose **Internal Dependencies** and **How to Extract** sections — those
describe the entanglement specific to this block.

### 2. Resolve `depends_on` transitively — always include `core`

Build the dependency closure:

```
to_pull = {X}
queue = depends_on(X)
while queue:
    b = queue.pop()
    if b in to_pull: continue
    to_pull.add(b)
    queue += depends_on(b)
always ensure: core ∈ to_pull
```

`core` is the shared multi-tenant substrate (config/settings, Fernet encryption,
`apply_workspace_scope`, `paginate`, the `deps.py` DI aliases, and the
automation event bus). Any block that touches workspaces, the DB, auth,
encryption, pagination, or automations needs it — so pull `core` unconditionally
even if a manifest forgot to list it.

### 3. Copy `owns_paths`

For every block in the closure, copy each entry in its `owns_paths` into the new
project, preserving the `backend/app/...` and `frontend/src/...` layout (or remap
to the new project's layout consistently). These are the files the block owns
outright — deleting the block would delete them.

Do **not** copy paths that belong to other blocks or to shared/core code unless
that block is in your closure.

### 4. Wire `public_api`

For each pulled block, register its `public_api` symbols in the new project:

- **Routers** (`...::router`) → `include_router(...)` in the new FastAPI app.
- **Service classes/functions** → import from their new location; check that
  callers in other pulled blocks still resolve.
- **Frontend components/hooks** → ensure routes under `src/app/<block>/` and
  components under `src/components/<block>/` are reachable and imported.

Anything **not** in a block's `public_api` is private; do not rely on it from
outside the block.

### 5. Set `env_vars`

Collect the union of `env_vars` across the closure plus the core vars the app
needs to boot (at minimum `SECRET_KEY`, `DATABASE_URL`, `ENCRYPTION_KEY`, and
`REDIS_URL`). Add them to the new project's `.env` / settings. For any
`external_integrations`, provision the corresponding credentials (e.g.
`RESEND_API_KEY` for Resend).

### 6. Port `db_tables` and migrations

- Create the tables listed in each block's `db_tables` by copying the
  corresponding `app/models/*.py` files (already done in step 3 if they are in
  `owns_paths`).
- Migrations: today the repo uses **one shared linear Alembic chain** in
  `backend/alembic/versions/` — there is no per-block migration split. So either
  (a) generate a fresh `alembic revision --autogenerate` against the pulled
  models in the new project, or (b) cherry-pick the specific revisions named in
  each block's `alembic_migrations` field and re-stitch their `down_revision`
  pointers into a clean chain. Option (a) is usually less error-prone for a new
  project.

### 7. Register `workers`

For each worker file in the closure's `workers` lists, register it in the new
project's worker runner (the equivalent of `start_all_workers()` /
`app.workers.runner:main`). Workers share a common base and a single
registration point, so confirm each pulled worker is added to that registry and
gated on the new project's `RUN_BACKGROUND_WORKERS` equivalent.

### 8. Verify

- App boots (`/readyz` equivalent returns non-500).
- Each pulled router's endpoints respond with the expected auth/workspace
  behavior.
- Workers start without import errors.
- No imports remain that point back into blocks you did **not** pull.

---

## Worked example: extract the `reviews` block

**Instruction:** *"Pull the reviews block into a new project."*

### Step 1 — Read `BLOCK.md`

The reviews manifest declares (see `BLOCK_SCHEMA.md` for the full example):

- `owns_paths`:
  - `backend/app/services/reviews/`
  - `backend/app/api/v1/reviews.py`
  - `backend/app/models/review.py`
  - `backend/app/models/review_request.py`
  - `backend/app/workers/review_request_worker.py`
  - `backend/app/workers/reputation_worker.py`
  - `frontend/src/components/reviews/`
  - `frontend/src/app/reviews/`
- `depends_on: [core, contacts, appointments, telephony, automations]`
- `external_integrations: [telnyx]` (review requests are sent as SMS)
- `env_vars: []` (Telnyx credentials are owned by the `telephony` block)
- `db_tables`: `review.py::reviews`, `review_request.py::review_requests`
- `workers`: `review_request_worker.py`, `reputation_worker.py`

### Step 2 — Resolve the closure

```
reviews → depends_on: core, contacts, appointments, telephony, automations
contacts → depends_on: core
appointments → depends_on: core
telephony → depends_on: core
automations → depends_on: core
core → depends_on: (none)
```

Closure = `{reviews, contacts, appointments, telephony, automations, core}`.
`core` is present (and would be added anyway).

### Step 3 — Copy owned paths

Copy all of reviews' `owns_paths` above, plus the `owns_paths` of `contacts`,
`appointments`, `telephony`, `automations`, and `core` (their
`app/models/contact.py`, `app/models/appointment.py`, `app/services/telephony/*`,
`app/models/automation*.py`, `app/core/*`, `app/db/*`, `app/api/deps.py`,
`app/services/automations/events.py`, etc.). Preserve the directory layout.

### Step 4 — Wire the public API

- `include_router(reviews.router)` from `backend/app/api/v1/reviews.py` into the
  new FastAPI app.
- Import `ReviewService` from `backend/app/services/reviews/review_service.py`
  where the router and workers use it.
- Make `frontend/src/app/reviews/` routes reachable and ensure
  `frontend/src/components/reviews/` imports resolve.

### Step 5 — Sever sideways imports

From the manifest's **Internal Dependencies** section, expect these concrete
sideways imports in `review_service.py`:

- `from app.models.contact import Contact` and
  `from app.models.appointment import Appointment` → satisfied because
  `contacts` and `appointments` are in the closure.
- `from app.services.telephony.telnyx import TelnyxSMSService` and
  `from app.services.calendar.reminder_service import resolve_from_number` —
  review requests are sent as **SMS**, so the `telephony` block (and the
  from-number resolver) must come along. This is the biggest entanglement.
- `from app.services.rate_limiting.opt_out_manager import OptOutManager` and
  `from app.services.notifications import notify_workspace_event` — pull these
  helpers or stub them; they gate sending on opt-out and notify operators.
- Review events emitted through the **core automation bus**:
  `emit_automation_event(db, workspace_id=..., event_type="review_received", ...)`
  from `app/services/automations/events.py`. Keep this — it goes through `core`
  rather than importing the automation worker directly. If you did **not** pull
  the `automations` block, the event row would simply never be drained; the
  emit call itself still works because it lives in `core`.
- Workspace scoping via `apply_workspace_scope` / `select_workspace_owned`, DB
  session via `DB`, and auth via `WorkspaceAccess`/`CurrentUser` from
  `app/api/deps.py` → all satisfied by `core`.

Confirm no remaining `from app.services.<other>...` import points at a block
outside the closure (e.g. campaigns, offers, voice).

### Step 6 — Env vars

Reviews owns no env vars directly. Its outbound SMS path needs the `telephony`
block's Telnyx credentials (`TELNYX_API_KEY` and related), plus the core boot
vars `SECRET_KEY`, `DATABASE_URL`, `ENCRYPTION_KEY`, `REDIS_URL`.

### Step 7 — DB + migrations

Models `review.py` and `review_request.py` create the `reviews` and
`review_requests` tables; `contacts` and `automations` bring their own tables.
Generate a fresh autogenerated migration in the new project against the pulled
models (cleaner than cherry-picking from the shared chain).

### Step 8 — Register workers

Add `review_request_worker` and `reputation_worker` to the new project's worker
runner and gate them on `RUN_BACKGROUND_WORKERS`. `reputation_worker`
recomputes reputation; `review_request_worker` sends/chases review requests.

### Step 9 — Verify

Boot the app, hit the reviews endpoints with a workspace-scoped token, confirm
the two workers start clean, and confirm no import reaches back into an
un-pulled block.

---

## Rules of thumb

- **Always pull `core`.** It is the floor every block stands on.
- **Trust `owns_paths` for what to copy, `public_api` for what to call.**
  Private internals are not your contract.
- **The hard part is `Internal Dependencies`, not `owns_paths`.** Sideways
  imports into other blocks decide the real effort; that is why
  `extraction_effort` and `extraction_notes` exist.
- **Prefer emitting through `core`** (the automation event bus) over importing
  another block's worker — it keeps blocks decoupled.
- **Migrations are a shared linear chain today.** Regenerate in the new project
  rather than assuming a clean per-block migration set exists.
