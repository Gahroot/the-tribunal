---
id: <kebab-case-block-id>
name: <Human Readable Name>
tier: <A|B|C|core>
status: <manifest|decoupled|extracted|service>
summary: <One or two sentences: what this block does.>
owns_paths:
  - backend/app/services/<block>/
  - backend/app/api/v1/<block>.py
  - backend/app/models/<model>.py
  - frontend/src/components/<block>/
  - frontend/src/app/<block>/
public_api:
  - backend/app/api/v1/<block>.py::router
  - backend/app/services/<block>/<service>.py::<ServiceClass>
  - frontend/src/components/<block>/<Component>.tsx::<Component>
depends_on: [core]            # add other block ids; keep core if it uses workspace/db/auth
external_integrations: []     # e.g. telnyx, stripe, cal.com, openai, elevenlabs, resend, follow-up-boss, mac-relay
env_vars: []                  # block-specific env var names read via settings
db_tables:
  - backend/app/models/<model>.py::<table_name>
alembic_migrations: shared chain — no per-block split yet   # or list revisions that create this block's tables
workers: []                   # backend/app/workers/<worker>.py files this block owns
extraction_effort: <low|medium|high>
extraction_notes: <One sentence flagging the biggest extraction hazard.>
---

## Overview

<What this capability does and why it exists, in product terms. 2–4 sentences.>

## Internal Dependencies

<Sideways imports into OTHER blocks (not core) that must be severed to extract.
List concrete imports and what each is used for.>

- `from app.services.<other_block>... import ...` — <why / what it does>
- <shared enum / shared model / cross-block helper> — <impact if extracted>

## Public Surface

<Expand on public_api. List routes, exported functions, components, and what
callers depend on.>

- Routes: `<METHOD> /api/v1/<block>/...`
- Services: `<ServiceClass>.<method>(...)`
- Frontend: `<Component>`, `<useHook>`

## How to Extract

1. Pull `core` (always) and every block in `depends_on`, transitively.
2. Copy each path in `owns_paths`.
3. Sever the sideways imports listed under Internal Dependencies.
4. Wire `public_api` symbols into the new project's router/registry.
5. Set `env_vars` in the new project's environment.
6. Port `db_tables` and the relevant migrations.
7. Register `workers` in the new project's worker runner.

## Risks

<Data, tenancy, migration, or integration risks when pulling this out.>
