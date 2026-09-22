# `app.core_api` — the core facade

**This is the ONLY surface other blocks may import core primitives from.**

Every non-core block (campaigns, voice, appointments, billing, automations
consumers, …) must import workspace/db/auth/worker/vault/event-bus primitives
from `app.core_api`, never from the deep internal modules behind it.

```python
# ✅ Do this
from app.core_api import DB, CurrentUser, get_workspace, apply_workspace_scope, settings

# ❌ Not this
from app.api.deps import DB, CurrentUser, get_workspace
from app.db.scope import apply_workspace_scope
from app.core.config import settings
```

## Why

The core block (`backend/app/core/`, `backend/app/db/`, `app/api/deps.py`, the
worker base, idempotency, and the automation event bus) is the multi-tenant
substrate every other block stands on. When consumers reach into arbitrary
internal paths, the public surface becomes implicit and unenforceable — any
internal refactor risks breaking distant blocks. This facade makes the contract
explicit and named: internal core modules are **private** to the core block, and
only the names re-exported here are public.

## What's exported

`app.core_api` re-exports the real public names (no renames, no invented names)
from these internal modules:

| Internal module | Re-exported names |
|---|---|
| `app.api.deps` | `DB`, `TransactionalDB`, `CurrentUser`, `ActiveUser`, `OptionalCurrentUser`, `WorkspaceAccess`, `WorkspaceAdminAccess`, `CurrentMembership`, `get_workspace`, `get_workspace_admin`, `get_membership`, `get_current_user`, `get_current_active_user`, `get_optional_current_user` |
| `app.db.scope` | `apply_workspace_scope`, `select_workspace_owned`, `get_workspace_owned`, `assert_workspace_owned` |
| `app.db.pagination` | `paginate`, `paginate_rows`, `PaginationResult`, `list_response` |
| `app.db.session` | `AsyncSessionLocal`, `get_db`, `transaction_boundary` |
| `app.core.config` | `settings`, `Settings`, `get_settings` |
| `app.core.encryption` | `EncryptedString`, `LookupHash`, `encrypt_json`, `decrypt_json`, `hash_value`, `hash_phone`, `hash_value_or_none`, `InvalidToken` |
| `app.services.idempotency` | `derive_outbound_key`, `derive_worker_retry_key`, `derive_webhook_delivery_key`, `idempotency_headers`, `encode_client_state`, `resolve_message_idempotency`, `claim_redis_idempotency_key`, `MessageIdempotencyState`, `RedisIdempotencyClaim`, plus the namespace/header/TTL constants |
| `app.workers.base` | `BaseWorker`, `WorkerRegistry` |
| `app.services.automations.events` | `emit_automation_event`, the `EVENT_*` trigger constants, `AUTOMATION_EVENT_TRIGGERS` |

The canonical list is `app.core_api.__all__`.

## Scope / not-yet-done

This facade is additive. Existing consumers that still import the deep internal
paths continue to work; migrating them to `app.core_api` is a follow-up. New code
should import from `app.core_api` only.

## Circular imports

The facade imports every core primitive at module top-level and imports cleanly
(verified via `uv run python -c "import app.core_api"`). If a future export
introduces a circular import, do **not** add a top-level import for it — expose
it lazily via a small accessor function defined in `__init__.py`, e.g.:

```python
def get_<thing>():
    from app.<module> import <thing>
    return <thing>
```

and document the lazy export here. As of this writing, **no symbol requires lazy
export.**
