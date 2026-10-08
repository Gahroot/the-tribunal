# RF-032: brand defaults

## Shipped policy

- Creating the first membership sets its stored `is_default=True`. Creating
  another brand, accepting another invitation, or running a seed helper keeps
  the existing default. Creating a brand does **not** select the current brand.
- `set-default` is the explicit replacement operation. It rechecks membership
  under a user-row `FOR UPDATE` lock and updates every flag for that user in
  the caller's transaction. Concurrent replacements serialize; the last
  committed replacement wins. Removing a flagged membership selects the
  remaining effective default in that same transaction.
- Every membership writer (API creation, invitations, personal provisioning,
  database seed, Prestyj demo seed, promotion QA seed) uses the shared helper.
  Locking the user also covers the empty-membership case; locking only existing
  memberships would not prevent two concurrent first brands. Helpers flush,
  never commit. Creation still provisions both pipeline and agent atomically.
- Login `/auth/me` and the workspace list expose one **effective active default**:
  oldest flagged active membership; otherwise oldest active membership. Order
  is `(created_at ASC, membership.id ASC)` to break timestamp ties. Reads never
  repair stored flags. Empty active membership lists have no default.
- Stored/current-brand selection still takes precedence in the frontend (RF-033).
  Changing the personal default does not switch the current brand.
- Billing deliberately keeps its historical resolver and owner/admin checks.
  No Stripe workspace/customer/subscription records are moved. Historical
  inactive/default billing accounts are not silently replaced by login's active
  projection. Explicit default selection continues to affect legacy billing
  lookup as before; explicit billing account selection belongs to RF-031.

## Legacy data and deferred constraint: approval required

No live defaults are rewritten, no backfill is shipped, and no migration is
required for this patch. New writes starting from valid data preserve one stored
flag. Legacy duplicate/zero flags remain stored until an explicit selection;
UI/login expose only one effective default. Arbitrary SQL can still bypass the
application invariant until a database constraint is approved and deployed.

Proposed deterministic repair (not authorized or executed):

1. Read-only inventory: count users with zero or multiple flags; export each
   membership's ID, timestamps, active status, flags and the exact historical
   billing workspace/customer pairing. Flag inactive billing accounts and
   timestamp ties for operator review rather than moving payments by inference.
2. For duplicates retain the oldest currently flagged membership, ordering by
   `created_at, id`; for zero flags propose the oldest membership using that
   order. Do **not** automatically replace an inactive historical default.
   For historical timestamp ties, require confirmation of the billing pairing
   before applying the UUID tie-break. Record every before/after flag.
3. Obtain explicit approval for the exact repair command and affected counts,
   plus a verified backup/PITR point for that database. Restore that backup to
   an isolated local database and test the repair, rollback and billing pairing
   comparison before touching real data.
4. Repair in bounded, restartable per-user transactions taking the same user
   lock; abort if membership state differs from the approved inventory. Never
   update `workspace_integrations` or Stripe objects. Retain the audit manifest
   for a separately approved compensating rollback.
5. Deploy a new Alembic migration only after reconciliation: a PostgreSQL partial
   unique index on `workspace_memberships(user_id) WHERE is_default`. Use
   `CREATE UNIQUE INDEX CONCURRENTLY` outside the migration transaction, bounded
   lock/statement timeouts, explicit invalid-index detection/recovery, and local
   upgrade/downgrade testing. This enforces **at most** one flag; application
   membership lifecycle still supplies the first default. Change the explicit
   setter to clear/flush then set/flush under the same lock before adding this
   index, since uniqueness is immediate. Test the migration and concurrent
   setters together and require approval before deploying real-data DDL.

## Working-code reference

Referenced through Steroids: [Vexa's async user-row locking dependency](https://github.com/Vexa-ai/vexa/blob/c1d0ef6f0456cc7907e89e0fa911f069597c7297/core/identity/services/admin-api/src/admin_api/app/main.py#L101-L112)
uses SQLAlchemy `select(User).with_for_update()` within the request session,
with `populate_existing=True` for loaded rows. RF-032 applies the user-row lock
as the membership serialization point and refreshes membership query results
under that lock; PostgreSQL fixture tests verify the blocking behavior.

## Local verification

Normal backend suite: `tests/api/test_workspace_defaults.py` plus existing
billing authorization/multiple-default tests. Frontend provider regression
proves default changes do not switch the current brand.

PostgreSQL suite:

```sh
cd backend
uv run pytest -m integration tests/integration/test_workspace_defaults_postgres.py
```

Uses only loopback `tribunal_inbox_test`, a random `rf032_*` schema, and fixture
rows. The configured application database is never used. Covers first/second
brands, provisioning, invitation first/additional/replayed joins, duplicates,
unchanged Stripe mapping, explicit replacements, concurrent creation/setters,
user-row blocking, concurrent personal provisioning and failed-create rollback.
The same fixture can be served on loopback port 8032 for HTTP eyes verification:
`uv run python -m tests.integration.test_workspace_defaults_postgres`.

Verification recorded 2026-10-08:

- Backend Ruff lint/format and mypy passed; 80 affected API/onboarding tests
  passed; all 15 PostgreSQL fixture tests passed. Coverage includes inactive defaults, zero-default
  rows, UUID timestamp ties, nonmember denial and default-member removal.
- HTTP eyes observed two 201 creations, list flags `[true, false]`, then a
  200 explicit default change and `/auth/me` resolving Brand B. Fixture logs
  confirmed pipeline/agent provisioning and no tracebacks.
- Frontend downstream CI commands passed on Node 20.20.2: lint (47 warnings,
  zero errors), typecheck, 732 tests and production build. `make ci.codegen`
  passed with no generated contract changes.
- `make ci.backend` and `make ci.frontend` were both attempted and stopped at
  existing `ci.env` template drift (five model-setting variables). Direct
  downstream backend checks also found two broken import-boundary contracts
  outside this patch. The full backend test run reported 3,454 passing,
  15 failing, seven errors and 16 skipped, with 63.88% coverage. Failures/errors
  were outside the affected membership tests (realtime token, outbound,
  ad-transparency, nudges, environment drift, idempotency, Resend fixture/router
  `handle_event` mismatch). These unrelated issues were not changed.
- No database metadata/schema changed, so `ci.migrations` was not run: that
  target operates on the configured application database and is unnecessary
  here. Only isolated schemas in the guarded local fixture database were
  created/dropped. No application/live data backfill or DDL was executed.
