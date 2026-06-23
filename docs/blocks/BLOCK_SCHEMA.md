# BLOCK.md Schema

This document defines the **block manifest** convention for The Tribunal. A
*block* is a self-contained capability folder (reviews, voice campaigns, offers,
billing, …). Every block gets a single `BLOCK.md` file at its conceptual root
that an AI agent can parse to extract that capability into a new project.

The goal: make the repo **agent-extractable**. Given "pull block X into a new
project," an agent reads `BLOCK.md`, resolves dependencies, copies the owned
paths, wires the public API, and ports DB/workers — without re-reading the whole
codebase.

This is a **documentation convention only**. Adding a `BLOCK.md` never changes
runtime behavior. Code is not refactored to satisfy it; the manifest describes
reality (including the messy parts) so extraction can be planned honestly.

---

## File format

A `BLOCK.md` has two parts:

1. **YAML frontmatter** — strict, machine-parseable metadata (the contract).
2. **Prose sections** — human- and agent-readable extraction guidance.

The frontmatter is delimited by `---` lines at the very top of the file. All
keys below are **required**; use an empty list `[]` or `null` where a field does
not apply rather than omitting the key, so parsers can rely on a fixed shape.

### Frontmatter fields

| Field | Type | Rules |
|---|---|---|
| `id` | string | **kebab-case**, globally unique across blocks (e.g. `reviews`, `voice-campaigns`). This is the value other blocks reference in `depends_on`. |
| `name` | string | Human-readable name (e.g. `Reviews & Reputation`). |
| `tier` | enum | One of `A` \| `B` \| `C` \| `core`. `A` = headline/standalone-sellable capability, `B` = supporting capability, `C` = peripheral/nice-to-have, `core` = the shared tenancy/db/auth substrate every block depends on. |
| `status` | enum | One of `manifest` \| `decoupled` \| `extracted` \| `service`. `manifest` = documented only, still entangled. `decoupled` = sideways imports severed, extractable in place. `extracted` = has been pulled into a standalone package/project at least once. `service` = runs as its own deployable service. |
| `summary` | string | One or two sentences: what the block does. |
| `owns_paths` | list[string] | Backend/frontend folders and files this block **owns** (repo-relative). Owning means: if you delete the block, these go with it. Do not list shared/core paths here. |
| `public_api` | list[string] | Exported symbols other code may legitimately call: routers, service functions, React components, hooks. Each entry is `path::symbol` or a route prefix. This is the block's stable surface. |
| `depends_on` | list[string] | Block `id`s this block needs. **Must include `core`** if the block uses workspace scoping, the DB session, auth/deps, encryption, or pagination (almost all do). |
| `external_integrations` | list[string] | Third-party services touched: `telnyx`, `stripe`, `cal.com`, `openai`, `elevenlabs`, `resend`, `follow-up-boss`, `mac-relay`. `[]` if none. |
| `env_vars` | list[string] | Environment variable names the block reads (via `settings`) — e.g. `RESEND_API_KEY`. Include only vars specific to this block, not core ones like `DATABASE_URL`. |
| `db_tables` | list[string] | Model files **and** table names this block owns, as `app/models/<file>.py::<table_name>`. |
| `alembic_migrations` | string | Free text. Today all blocks share one linear Alembic chain in `backend/alembic/versions/`; note which revisions create this block's tables, or state `shared chain — no per-block split yet`. |
| `workers` | list[string] | Background worker files in `app/workers/` this block owns, repo-relative. `[]` if none. |
| `extraction_effort` | enum | One of `low` \| `medium` \| `high`. Honest estimate of how hard it is to pull out given current entanglement. |
| `extraction_notes` | string | One or two sentences flagging the biggest extraction hazard (shared enum, cross-block import, shared migration, etc.). |

### Prose sections (after frontmatter)

In this order, using `##` headings:

- **Overview** — what the capability does and why it exists, in product terms.
- **Internal Dependencies** — the **sideways imports** into other blocks (not
  `core`) that must be severed to extract. List concrete `from app...import`
  lines and what each is used for. This is the section that determines real
  effort.
- **Public Surface** — expand on `public_api`: routes, exported functions,
  components, and what callers rely on.
- **How to Extract** — an ordered, concrete checklist for this specific block.
- **Risks** — data, tenancy, migration, or integration risks when pulling it
  out.

---

## The `core` block

Almost every block depends on `core`. `core` is the shared multi-tenant
substrate. It is the one block that depends on nothing and that everything else
pulls in transitively. Its public surface (verify against source — these are the
real modules):

- **`backend/app/core/config.py`** — `settings` (Pydantic `BaseSettings`). All
  env vars, secrets, and integration keys are read here. `Settings.secret_key`
  is required; the app refuses to boot without it.
- **`backend/app/core/encryption.py`** — Fernet credential vault.
  `EncryptedString` SQLAlchemy column type, `encrypt_json` / `decrypt_json`,
  `hash_value` / `hash_phone` lookup hashing. Per-workspace third-party
  credentials are encrypted at rest with `ENCRYPTION_KEY`.
- **`backend/app/db/scope.py`** — `apply_workspace_scope(query, model,
  workspace_id)` plus `select_workspace_owned` / `get_workspace_owned` /
  `assert_workspace_owned`. The tenancy boundary every workspace-owned query
  must pass through.
- **`backend/app/db/pagination.py`** — `paginate(db, query, page, page_size)`
  and `paginate_rows`, returning `PaginationResult` with `.to_response(Model)` /
  `.build_response(...)`.
- **`backend/app/api/deps.py`** — dependency-injection aliases: `DB`,
  `CurrentUser`, `ActiveUser`, `WorkspaceAccess` (via `get_workspace`),
  `WorkspaceAdminAccess`, `CurrentMembership`, `TransactionalDB`. These enforce
  auth + workspace membership on every authenticated route.
- **`backend/app/services/automations/events.py`** —
  `emit_automation_event(db, workspace_id=..., event_type=..., ...)`, the
  automation event bus. Blocks that should trigger automations emit events here
  (e.g. `review_received`) instead of importing the automation worker.

Any block that uses workspace scoping, the DB session, auth, encryption,
pagination, or the automation bus **must** declare `depends_on: [core, ...]`.

---

## Minimal example

```yaml
---
id: reviews
name: Reviews & Reputation
tier: A
status: manifest
summary: Collects, requests, and analyzes customer reviews; tracks reputation per workspace.
owns_paths:
  - backend/app/services/reviews/
  - backend/app/api/v1/reviews.py
  - backend/app/models/review.py
  - backend/app/models/review_request.py
  - backend/app/workers/review_request_worker.py
  - backend/app/workers/reputation_worker.py
  - frontend/src/components/reviews/
  - frontend/src/app/reviews/
public_api:
  - backend/app/api/v1/reviews.py::router
  - backend/app/services/reviews/review_service.py::ReviewService
depends_on: [core, contacts, appointments, telephony, automations]
external_integrations: [telnyx]
env_vars: []
db_tables:
  - backend/app/models/review.py::reviews
  - backend/app/models/review_request.py::review_requests
alembic_migrations: shared chain — no per-block split yet
workers:
  - backend/app/workers/review_request_worker.py
  - backend/app/workers/reputation_worker.py
extraction_effort: medium
extraction_notes: Review requests are dispatched as SMS via the telephony block's TelnyxSMSService (a sideways import); also depends on resolve_from_number, OptOutManager, and notifications. Emits review_received via the core automation bus.
---
```

See `_TEMPLATE.BLOCK.md` for a fill-in-the-blanks starting point and
`AGENT_EXTRACTION_GUIDE.md` for how an agent consumes these manifests.
