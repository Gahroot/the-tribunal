---
id: core
name: Core (Multi-Tenant Substrate)
tier: core
status: manifest
summary: The shared multi-tenant substrate every other block stands on — settings/config, the Fernet credential vault, workspace scoping, DB session + pagination, auth/DI dependencies, idempotency, the outbound HTTP provider layer, and the background-worker runtime. Depends on nothing; everything depends on it.
owns_paths:
  - backend/app/core/
  - backend/app/db/
  - backend/app/api/deps.py
  - backend/app/services/idempotency.py
  - backend/app/services/providers/
  - backend/app/workers/base.py
  - backend/app/workers/retryable.py
  - backend/app/workers/runner.py
  - backend/app/workers/__init__.py
  - backend/app/models/workspace.py
  - backend/app/models/user.py
  - backend/app/models/refresh_token.py
  - backend/app/models/api_key.py
public_api:
  - backend/app/api/deps.py::DB
  - backend/app/api/deps.py::TransactionalDB
  - backend/app/api/deps.py::CurrentUser
  - backend/app/api/deps.py::ActiveUser
  - backend/app/api/deps.py::WorkspaceAccess
  - backend/app/api/deps.py::WorkspaceAdminAccess
  - backend/app/api/deps.py::CurrentMembership
  - backend/app/api/deps.py::get_workspace
  - backend/app/db/scope.py::apply_workspace_scope
  - backend/app/db/scope.py::select_workspace_owned
  - backend/app/db/scope.py::get_workspace_owned
  - backend/app/db/scope.py::assert_workspace_owned
  - backend/app/db/pagination.py::paginate
  - backend/app/db/pagination.py::paginate_rows
  - backend/app/db/pagination.py::PaginationResult
  - backend/app/db/pagination.py::list_response
  - backend/app/db/session.py::AsyncSessionLocal
  - backend/app/db/session.py::get_db
  - backend/app/db/session.py::transaction_boundary
  - backend/app/db/base.py::Base
  - backend/app/db/redis.py::get_redis
  - backend/app/db/model_registry.py::import_model_modules
  - backend/app/core/config.py::settings
  - backend/app/core/config.py::Settings
  - backend/app/core/encryption.py::EncryptedString
  - backend/app/core/encryption.py::LookupHash
  - backend/app/core/encryption.py::encrypt_json
  - backend/app/core/encryption.py::decrypt_json
  - backend/app/core/encryption.py::hash_value
  - backend/app/core/encryption.py::hash_phone
  - backend/app/core/security.py::create_access_token
  - backend/app/core/security.py::decode_access_token
  - backend/app/core/security.py::verify_password
  - backend/app/core/security.py::get_password_hash
  - backend/app/core/rate_limit_helpers.py::raise_rate_limited
  - backend/app/core/circuit_breakers.py::ProviderCircuitBreaker
  - backend/app/core/webhook_security.py::verify_telnyx_webhook
  - backend/app/core/request_id.py::generate_ulid
  - backend/app/core/logging.py::configure_logging
  - backend/app/services/idempotency.py::derive_outbound_key
  - backend/app/services/idempotency.py::derive_worker_retry_key
  - backend/app/services/idempotency.py::derive_webhook_delivery_key
  - backend/app/services/providers/http.py::ProviderHTTPError
  - backend/app/workers/base.py::BaseWorker
  - backend/app/workers/base.py::WorkerRegistry
  - backend/app/workers/retryable.py::RetryableWorker
  - backend/app/workers/__init__.py::start_all_workers
  - backend/app/workers/__init__.py::stop_all_workers
  - backend/app/workers/runner.py::main
depends_on: []
external_integrations: []
env_vars:
  - SECRET_KEY
  - DATABASE_URL
  - ENCRYPTION_KEY
  - REDIS_URL
  - RUN_BACKGROUND_WORKERS
db_tables:
  - backend/app/models/workspace.py::workspaces
  - backend/app/models/workspace.py::workspace_memberships
  - backend/app/models/workspace.py::workspace_integrations
  - backend/app/models/user.py::users
  - backend/app/models/refresh_token.py::refresh_tokens
  - backend/app/models/api_key.py::api_keys
alembic_migrations: shared linear chain — workspaces + workspace_memberships + workspace_integrations + users (e6c0ca7dd25e_initial_schema), refresh_tokens (rt01a1b2c3d4_add_refresh_token_table), api_keys (b3c4d5e6f7a8_add_api_keys_table). The entire chain lives in backend/alembic/versions/ and is owned operationally by core.
workers: []
extraction_effort: low
extraction_notes: Core depends on nothing and is the mandatory floor of every closure — it is always pulled, never severed. The hazard is the reverse: forgetting to pull it. Every other block imports app.api.deps, app.db.scope/pagination/session, app.core.config.settings, app.core.encryption, app.services.idempotency, and the app.workers base/registry, so core must be copied first and wholesale.
---

## Overview

Core is the shared multi-tenant substrate of The Tribunal. It is not a product capability — it is the floor every capability stands on. It owns configuration/secrets (`app/core/config.py::settings`), the Fernet credential vault that encrypts per-workspace third-party credentials at rest (`app/core/encryption.py`), the workspace tenancy boundary (`app/db/scope.py`), the async DB session and pagination helpers (`app/db/session.py`, `app/db/pagination.py`), Redis access (`app/db/redis.py`), the auth + workspace-membership dependency-injection aliases every authenticated route uses (`app/api/deps.py`), idempotency-key derivation (`app/services/idempotency.py`), the resilient outbound HTTP provider layer with circuit breakers (`app/services/providers/`, `app/core/circuit_breakers.py`), request-id/logging/security primitives, and the background-worker runtime (`app/workers/base.py`, `retryable.py`, `runner.py`, and `start_all_workers()` in `app/workers/__init__.py`). It also owns the foundational tenancy/auth models: `workspace.py` (workspaces, memberships, encrypted integrations), `user.py`, `refresh_token.py`, and `api_key.py`.

**Core is the mandatory dependency of every other block.** Any block that touches workspaces, the DB session, auth, encryption, pagination, Redis, idempotency, or the worker runtime declares `depends_on: [core, ...]` — which in practice is all of them.

## Internal Dependencies

None. Core has no sideways imports into other blocks (`depends_on_blocks: []` in `docs/blocks/coupling-report.json`). It is the root of the dependency graph: it imports only third-party libraries and standard library, never `app.services.<other_block>` or `app.models.<domain>`. The automation event bus (`app/services/automations/events.py`) is documented as a `core`-level seam in `BLOCK_SCHEMA.md` but is owned by the `automations` block; core itself does not import it.

## Public Surface

This is the import surface other blocks are allowed to use. Everything else under `app/core/` and `app/db/` is internal plumbing.

- **DI / auth** (`app/api/deps.py`): `DB`, `TransactionalDB` (session aliases), `CurrentUser`, `ActiveUser`, `WorkspaceAccess` / `WorkspaceAdminAccess` / `CurrentMembership` (via `get_workspace` / `get_workspace_admin` / `get_membership`). Every authenticated route depends on these for auth + workspace membership enforcement.
- **Tenancy** (`app/db/scope.py`): `apply_workspace_scope(query, model, workspace_id)`, `select_workspace_owned`, `get_workspace_owned`, `assert_workspace_owned` — the boundary every workspace-owned query must pass through.
- **Pagination** (`app/db/pagination.py`): `paginate`, `paginate_rows`, `PaginationResult` (`.to_response` / `.build_response`), `list_response`.
- **DB session / base** (`app/db/session.py`, `app/db/base.py`, `app/db/redis.py`, `app/db/model_registry.py`): `AsyncSessionLocal`, `get_db`, `transaction_boundary`, `Base`, `get_redis`, `import_model_modules`.
- **Config / secrets** (`app/core/config.py`): `settings` (Pydantic `BaseSettings`; `secret_key` required — the app refuses to boot without it), `Settings`.
- **Encryption** (`app/core/encryption.py`): `EncryptedString` / `LookupHash` SQLAlchemy column types, `encrypt_json` / `decrypt_json`, `hash_value` / `hash_phone` lookup hashing.
- **Security** (`app/core/security.py`): JWT `create_access_token` / `decode_access_token`, refresh-token helpers, `verify_password` / `get_password_hash`.
- **Resilience / safety** (`app/core/circuit_breakers.py`, `rate_limit_helpers.py`, `webhook_security.py`, `request_id.py`, `logging.py`): provider circuit breakers, `raise_rate_limited`, webhook-signature verification, ULID/request-id generation, structured logging with redaction.
- **Idempotency** (`app/services/idempotency.py`): `derive_outbound_key`, `derive_worker_retry_key`, `derive_webhook_delivery_key`.
- **HTTP provider layer** (`app/services/providers/http.py`): `ProviderHTTPError` and subclasses, timeout/retry helpers for all third-party calls.
- **Worker runtime** (`app/workers/base.py`, `retryable.py`, `runner.py`, `__init__.py`): `BaseWorker`, `WorkerRegistry`, `RetryableWorker`, `start_all_workers()` / `stop_all_workers()`, and the `app.workers.runner:main` console-script entrypoint.

## How to Extract

1. Core is always the first thing pulled, for every block. Copy all of `owns_paths` wholesale — do not cherry-pick files; the modules are interdependent.
2. Set the boot env vars: `SECRET_KEY` (required, ≥32 chars), `DATABASE_URL`, `ENCRYPTION_KEY`, `REDIS_URL`, and `RUN_BACKGROUND_WORKERS`.
3. Stand up Postgres (with pgvector if any pulled block needs it) and Redis 7.x.
4. Create the tenancy/auth tables (`workspaces`, `workspace_memberships`, `workspace_integrations`, `users`, `refresh_tokens`, `api_keys`) by porting the four model files; generate a fresh autogenerated migration in the new project rather than cherry-picking the shared chain.
5. Wire `app.api.deps` aliases into the new FastAPI app and register `start_all_workers()` in the lifespan (gated on `RUN_BACKGROUND_WORKERS`), plus the `app.workers.runner:main` console script for a split worker process.
6. Confirm `/readyz` (or its equivalent) returns non-500 and that auth + workspace-scoped routes resolve before pulling any other block on top.

## Risks

- **Boot-blocking config:** `settings.secret_key` has no default; a missing `SECRET_KEY` (or sub-32-char value) crashes startup by design. `ENCRYPTION_KEY` defaults to a placeholder — set a real Fernet key or every encrypted credential round-trips against an insecure key.
- **Tenancy correctness:** `apply_workspace_scope` / `select_workspace_owned` are the only thing standing between workspaces' data; any pulled block that queries a workspace-owned table without going through them risks cross-tenant leakage.
- **Credential vault coupling:** `EncryptedString` columns and `encrypt_json`/`decrypt_json` are keyed by `ENCRYPTION_KEY`; rotating or losing it makes all per-workspace integration secrets unreadable (see `make rotate.encryption-key`).
- **Worker fan-out:** `start_all_workers()` runs ~27 in-process poll loops; deploying with `--workers > 1` or multiple replicas multiplies every loop. Split workers out via `RUN_BACKGROUND_WORKERS=false` + `uv run backend-workers` (see CLAUDE.md).
- **Shared migration chain:** core owns the operational Alembic chain in `backend/alembic/versions/`; in an extraction, regenerate rather than re-stitching `down_revision` pointers.
