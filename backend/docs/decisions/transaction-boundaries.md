# Backend transaction boundaries

## Convention

Transaction ownership belongs to the outermost application unit of work:

- HTTP routers own request-level transactions for migrated routes by accepting `TransactionalDB` from `app.api.deps` instead of `DB` on mutating handlers.
- Background workers, webhook consumers, WebSocket handlers, CLI scripts, and tests own their own explicit unit-of-work boundary. Use `transaction_boundary(session)` from `app.db.session` when a shared helper is useful.
- Services and repositories do not call `commit()` or `rollback()`. They may call `flush()` when they need database-generated values, constraint checks, or ORM state that must exist before returning. They may call `refresh()` after a flush when response serialization needs server-side defaults.
- Avoid nested ownership. A service that must be reusable from routers, workers, and tests should assume the caller decides whether the unit of work commits or rolls back.
- Expected domain validation should raise before the boundary commits. Unexpected exceptions should propagate so the boundary rolls back.

`DB` remains available for read-only routes and legacy code. New or migrated mutating HTTP routes should use `TransactionalDB`; do not add new service-level commits for router paths.

## Helper APIs

- `transaction_boundary(session)` wraps one unit of work and commits any open transaction on success.
- The same helper rolls back any open transaction on exceptions and also rolls back if commit itself fails.
- `get_transactional_db()` exposes that helper to FastAPI and is intentionally declared with `scope="function"` through the `TransactionalDB` alias so commit/rollback happens after the endpoint returns but before the response is sent.

## Audit snapshot (2026-06-01)

A repository grep for `.commit(`, `.rollback(`, and `.flush(` showed mixed ownership before this convention:

| Layer | Files with transaction calls | Commits | Rollbacks | Flushes |
| --- | ---: | ---: | ---: | ---: |
| `backend/app/api/v1` | 30 | 105 | 0 | 16 |
| `backend/app/api/webhooks` | 4 | 12 | 0 | 1 |
| `backend/app/services` | 59 | 141 | 7 | 50 |
| `backend/app/workers` | 18 | 27 | 2 | 1 |
| `backend/app/websockets` | 1 | 2 | 0 | 0 |

The counts confirm routers and services have historically both owned commits. The migration path is intentionally incremental: pick one domain, remove service/repository commits, and switch only its mutating router handlers to `TransactionalDB`.

## Representative migration

The tags domain is the first migrated domain:

- `backend/app/api/v1/tags.py` uses `TransactionalDB` on create, update, delete, and bulk mutation routes.
- `backend/app/services/tags/tag_repository.py` no longer commits; it flushes/refreshes only where needed.
- `backend/app/services/tags/` and `backend/app/api/v1/tags.py` should stay free of direct `commit()` and `rollback()` calls.

## Test expectations

- `backend/tests/db/test_transaction_boundary.py` proves commit-on-success, no-op read-only success, rollback-on-error, and rollback-on-commit-failure behavior.
- `backend/tests/services/tags/test_tag_transaction_boundary.py` proves migrated tag repository operations flush without committing.
