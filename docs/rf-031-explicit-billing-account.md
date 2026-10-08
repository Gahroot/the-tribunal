# RF-031: explicit legacy billing account

## Implemented compatibility boundary

ORG-001 (`.ezcoder/plans/multi-brand-organization-architecture.md`) specifies one company billing account above isolated brand workspaces. That organization/membership/billing mapping schema is not implemented. This fix does **not** provide shared company billing or infer a company from overlapping memberships.

`GET /api/v1/billing/account` exposes the current legacy account's workspace UUID, name, and `kind=workspace`. Without an explicit ID, discovery retains RF-030's default/oldest-membership resolution and authorizes that exact active workspace. An unapproved default is denied, not replaced by an owned sibling. With `billing_account_id`, discovery authorizes that exact account with no fallback.

Status and portal now require a UUID `billing_account_id` query parameter; checkout requires it in the body. Every operation independently applies the existing owner/admin, membership, active-workspace, and API-key workspace-binding checks **before** credentials or Stripe calls. These are legacy workspace permissions, not organization-owner permissions.

Settings and `/billing` display the account name and UUID, explain its independence from the sidebar, and state that shared company billing is unavailable. Account discovery is user/requested-account scoped; status cache keys include authenticated user and resolved account. Payment actions, Settings links, and Stripe return URLs retain that explicit ID, including across a default change. Failed resolution never enables payment controls.

Existing encrypted integration blobs, Stripe customer/subscription identifiers, workspace metadata/webhook routing, and CRM tenancy are unchanged. No records are merged/transferred, no database migration runs, and no real Stripe action is part of verification. Deploy the API and matching regenerated client together: older unscoped payment requests now fail validation rather than silently selecting an account.

## Remaining organization migration prerequisite

Before enabling company-wide billing, implement ORG-001's approved organization associations, authoritative owner/membership guards, and canonical SaaS billing mapping. First approve a restricted workspace → company → owner → existing SaaS customer/subscription reconciliation manifest. Do not infer grouping from a user, default brand, or payment-collection Stripe integration. Multiple paid customers/subscriptions and conflicting owners are blocked reconciliation cases requiring separate approval. Preserve existing IDs/blobs and distinguish SaaS billing from brand deposit/payment collection.

Only after fixture backfill/shadow verification may account discovery use that persisted organization account and organization-owner authority; then carry its identity through the same request/cache/display contract. Brand owner/admin is not company billing authority. No organization schema, entitlement policy, commercial consolidation, or provider transfer is invented here.

## Working-code reference

Inspected via `steroids`: `elizaOS/eliza`, `packages/cloud/api/v1/apps/[id]/billing/_handlers.ts`, lines 157–193. Its account resolver and snapshot/mutation handlers carry an explicit billing account scope alongside the authenticated actor. Reused that scope/actor boundary pattern with existing FastAPI guards, not its schema or dependencies.

## Verification scope

Existing backend billing API suite covers explicit targets with two brands, different defaults/sidebar context, owner/admin/member and unknown roles, absent memberships, inactive workspaces, API-key mismatch, no role-based fallback, required IDs, provider errors and matching status/checkout/portal customer targets. Existing frontend entry-point suite covers both billing surfaces, visible identity, sidebar changes, pinned return context, request IDs, permission errors and user/account cache separation.

Local HTTP evidence: `.ezcoder/eyes/out/rf031-http.json` (gitignored); synthetic server on `127.0.0.1:8031`, mocked DB and Stripe SDK, outbound socket connections denied. Account/status/checkout/portal return expected 200 shapes; member, inactive and omitted-target requests return 403/404/422. Mock URLs are never opened. Browser visual layout and real provider state are not verified.

Full `make ci.backend` and `make ci.frontend` initially stop on existing `ci.env` drift (missing five model settings in `backend/.env.example`). With that unrelated prerequisite excluded, backend Ruff/format/mypy pass but import-boundary checks stop on existing voice→calendar/knowledge and appointments→payments edges. Separate full pytest/coverage: 3,472 passed, 15 failed, 7 errors, 16 skipped, 104 integration cases deselected; coverage 63.89% exceeds the 48% gate. Failures/errors concern realtime-token, outbound mission/discovery, nudges, environment-script path, outbound growth, approval-worker mocks and Resend contract mocks, not billing. The final billing suite separately passes all 58 cases; its Ruff/format checks pass.

Final frontend CI with only `ci.env` and dependency-install prerequisites excluded passes lint (47 existing warnings, zero errors), typecheck, all 88 test files / 736 tests (20 billing entry-point cases), and production build. Installed dependencies are reused without running install/sync steps. Regeneration produces identical OpenAPI/client hashes. `make ci.codegen` is run after the generated changes are committed because its drift gate compares against Git HEAD.
