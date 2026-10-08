# Multi-brand organization architecture — proposed implementation plan

Status: **Plan only; implementation approval required.**
Date: 2026-10-08
Task: 5377d7d9

## 1. Approved direction and boundaries

One company/organization owns multiple brands, has one organization owner and one company SaaS billing account. Teammates access only explicitly permitted brands. Each brand keeps isolated CRM data, settings, integrations, sender identities, and operational configuration.

**Keep every existing workspace ID. A workspace is the brand container; do not move CRM records.** Existing foreign keys, public links, provider associations, API keys, and customer data remain anchored to their workspace. A login is a user identity, not a company identity: shared users, owners, email domains, default selections, or provider credentials never prove that two workspaces belong to the same organization.

This document proposes future schema/API/auth/billing work; it does not authorize any of it. No production migrations, data movement, provider calls, package installation, or product capabilities are part of this planning task. Cross-brand contact search, CRM merging, shared inboxes, cross-brand campaigns, analytics rollups, reseller hierarchies, and automatic subscription consolidation are out of scope. Preserve unrelated work, particularly `backend/app/websockets/call_supervisor.py`.

Evidence labels: **CODE** = inspected repository source, not executed proof; **REFERENCE** = inspected external working source; **PROPOSED** = design/test requirement, not implemented; **RUNTIME** = executed behavior (none gathered for this architecture).

## 2. Shared vocabulary and decision records

No tracked `CONTEXT.md` or `docs/adr/` records were found. Existing decision notes live in `backend/docs/decisions/`: `auth-rate-limit-cleanup.md`, `transaction-boundaries.md`, and `prestyj-batch-video-ads-offer-ladder.md` were read. They do not define organization/brand ownership or conflict with this design. Honor the transaction-boundary convention: new mutation routers use `TransactionalDB`; reusable services flush, never commit. Offer metadata stays brand-local.

Proposed glossary entries, contained here to keep this task to one planning artifact:

- **Organization** — the owning company, with one owner and one company SaaS billing account, containing one or more brands. Avoid: workspace, brand, login account.
- **Brand** — an isolated CRM and operational identity owned by exactly one organization. Avoid: company account, organization.
- **Workspace** — the existing persisted/API container implementing a brand; `workspace_id` remains its stable identifier. Avoid: using workspace to mean an organization.
- **Organization owner** — the single company-level authority for billing and brand/team administration; not inferred from brand membership.
- **Brand admin / brand member** — permission on a named workspace, not authority over sibling brands or company billing.
- **Organization membership** — association of a user with a company; by itself grants no sibling-brand CRM access.
- **Brand assignment** — explicit active workspace membership authorizing brand access.
- **Company billing account** — The Tribunal SaaS customer/subscription relationship, distinct from a brand's CRM contacts or payment-collection integration.
- **Entitlement** — company-level subscription permission/limit, consumed in a brand context; not a substitute for membership.
- **Provider identity** — brand-specific credential/resource/sender binding used for external operations; not the company SaaS billing identity.

Edge cases: a consultant assigned to Brands A and C in different companies has two organization memberships, not a combined company. Two brands selling the same offer remain separate CRM containers. A brand admin is not an organization owner. A brand's Stripe payment collection is not its parent company's SaaS subscription.

After approval, publish the settled glossary in `CONTEXT.md` and its instruction pointer, and propose a decision record following existing decision-note conventions for “organization ownership with unchanged workspace tenancy.” Keep that record separate from implementation approval. Rejected options: moving CRM rows to organization tenancy; treating all a user's workspaces as one company; giving all organization members all-brand access; inheriting billing authority from brand admin/owner roles. These lose isolation or create authority ambiguity.

## 3. What exists versus what is missing (CODE)

| Area | Existing evidence | Missing / readiness implication |
| --- | --- | --- |
| Brand containers | `backend/app/models/workspace.py`: UUID workspace PK, globally unique slug, settings/autonomy mandate, active flag, workspace-scoped CRM relationships | No organization FK/model; retaining tenancy is feasible, company ownership is absent |
| Assignments | Same file: unique `(user_id, workspace_id)` membership, free-form owner/admin/member role, per-membership default | No organization membership, singleton company owner, or company/brand role separation |
| Integrations | Same file: unique `(workspace_id, integration_type)` and Fernet-encrypted credentials | Encryption/isolation foundations exist, not verified end-to-end across every provider/fallback |
| Workspace APIs | `backend/app/api/v1/workspaces.py`: lists active memberships; any authenticated user can create a workspace and becomes owner/default; admin updates; owner soft-deactivates; team role/removal protections | Creation lacks company context/entitlements; creating a workspace can leave multiple defaults; brand owner is not company owner |
| Authorization | `backend/app/api/deps.py`: `get_workspace` checks membership and active workspace; admin dependency checks role; API-key workspace binding enforced in these dependencies | New company dependencies required; `get_membership` does not itself check active workspace; do not assume all routes use the canonical guards |
| Invitations | `backend/app/models/invitation.py`, schemas and `api/v1/invitations.py`: workspace-bound token, seven-day default expiry, admin/member input roles; delivery tracking/resend; acceptance requires matching authenticated email and creates one non-default membership | No company invitation/assignment set. Custom `verify_workspace_admin` checks membership/role but lacks the canonical API-key-binding and active-workspace checks; close this gap in approved auth work |
| Registration/login | `api/v1/auth.py:109–198`, `services/workspaces/provisioning.py:61–101`: auto-provision personal workspace when no membership; existing memberships reused; `/auth/me` supplies a default workspace ID | No company provisioning; invite signup can create an extra personal workspace; default is not billing authority |
| Onboarding | `api/v1/onboarding/realtor_setup.py:153–190`, `services/onboarding/workspace_setup.py`: explicit authorized workspace onboarding plus deprecated default-workspace route; brand-local agents/numbers/credentials/imports | Review credential/provisioning mutations for brand-admin requirement; legacy default resolution is unsuitable for multi-brand writes; provisioning may call/purchase from Telnyx |
| Frontend selection | `providers/workspace-provider.tsx`: authenticated membership list, stored selection validated by list lookup, default/first fallback, loading/empty/unavailable distinctions, cache clear on switch | No organization identity; global storage key/list key; stale in-flight work, forms, sockets, and account transitions need coverage |
| Switcher | `components/layout/workspace-switcher.tsx`: flat workspace list and unconditional Add workspace entry | Needs company-grouped permitted brands and server-derived creation capability; no inference from common user |
| Billing | `api/v1/billing.py`: default/oldest membership resolution; SaaS Stripe customer stored in workspace integration; checkout metadata uses workspace ID; portal/status query Stripe; signed webhook handles SaaS and payments | No explicit company context or owner check. Ordinary members can reach these handlers; status selects one subscription, not a canonical subscription model. Unsafe to carry this authority model forward |
| Billing client | `lib/api/billing.ts`, `components/shared/billing/use-billing.ts`, `lib/query-keys.ts`: unscoped status/checkout/portal and `['billing-status']` cache key | Selected brand currently does not determine billing workspace. Must use explicit organization and permission-aware contracts |
| Session changes | `providers/auth-provider.tsx:143–149`: logout clears user state; inspected callback does not clear React Query | User-scoped cache and stored-selection reset must be proven; hiding signed-out data alone is insufficient |

These are source observations, **not a claim that all CRM paths already isolate correctly**. Existing tests provide foundations, not proof of the proposed organization architecture.

### Working-code reference requested via steroids (REFERENCE)

Inspected `getnao/nao`, `apps/backend/src/queries/organization.queries.ts`, revision `59cf0d3aa6c7971600f1126eb853ed06f91fc435`, lines 28–110:
https://github.com/getnao/nao/blob/59cf0d3aa6c7971600f1126eb853ed06f91fc435/apps/backend/src/queries/organization.queries.ts#L28-L110

`getOrgMember` matches both organization and user; `listUserOrgMemberships` joins explicit membership rows to organizations; `addOrgMemberIfMissing` uses conflict-safe insertion. Apply the explicit membership and retry-safe association pattern with existing SQLAlchemy tools, not new dependencies. Do **not** copy its selected-organization fallback into mutating/billing authorization, or its first-organization/email-domain identity resolution. An invalid explicit organization must fail closed, never silently select another company. This reference supports patterns, not a complete billing or brand-isolation solution.

## 4. Proposed ownership and data model

Add an organization layer above, never in place of, workspace tenancy:

1. `Organization`: UUID, company name, active status, non-null `owner_user_id`. A single owner pointer is authoritative; no independent owner role flags that can disagree. Restrict owner deletion; prevent owner removal without an explicitly approved, audited transfer. Owner transfer UI/API is not part of initial scope.
2. `Workspace.organization_id`: initially nullable during expand/backfill, eventually non-null FK with restrictive deletion. Keep workspace PKs, global slug uniqueness, CRM FKs, and integration rows unchanged. Do not introduce company-wide CRM uniqueness/deduplication.
3. `OrganizationMembership`: unique `(organization_id, user_id)`, active association for teammates; owner must also have an active association. Start with owner/member semantics, no new company-admin/billing-admin delegation. Brand membership is the assignment authority.
4. Keep `WorkspaceMembership` rows/IDs and admin/member roles. Existing `owner` role remains a compatibility value until an approved conversion; never use it to authorize company billing. Proposed target maps legacy brand owner to brand admin after company ownership is explicitly resolved. Preserve a pre-conversion manifest. Do not silently demote ambiguous owners.
5. `OrganizationBillingAccount`: unique organization association with a canonical existing SaaS customer and subscription mapping; retain legacy workspace source references and immutable transition manifest. Store only necessary provider identifiers, encrypt secrets, restrict billing reads. Customer/provider-account/livemode mappings must be unambiguous; conflicting associations stop migration.

Database invariants: uniqueness on organization membership and billing account; checked brand roles; restrictive parent deletion; existing workspace membership uniqueness remains. Enforce organization membership plus workspace assignment as one transaction. Prefer a separate assignment service validating workspace parent under lock rather than duplicating organization ID into all CRM rows. If organization ID is duplicated into assignments/invitation targets, require composite FKs enforcing parent consistency. Owner association consistency and assignment revocation require transactional services and integrity tests, not only UI checks.

Organization owner controls company administration/billing and assignment of teammates. Proposed default: explicitly provision owner assignments to all company brands, including newly created brands, so CRM authorization still uses workspace membership; this owner-wide access policy needs approval (see decisions). Teammates do not inherit new brands. Removing an organization member atomically revokes their assignments and pending invites; brand-only removal leaves other assignments intact. Soft-deactivate, do not cascade-delete company/CRM records. Existing unlinked legacy workspaces remain in compatibility mode and cannot join another company implicitly.

## 5. Authorization, invitations, and onboarding

### Permission boundaries

| Actor | Assigned brand CRM | Brand settings/integrations | Assign brand teammates | Add brand / company settings | Company billing |
| --- | --- | --- | --- | --- | --- |
| Organization owner | Via explicit assignment | Via brand admin assignment | All brands in own company | Yes, subject to approved entitlement | Yes |
| Brand admin | Own assigned brands only | Own admin brands only | Own brand, admin/member only under approved policy | No | No |
| Brand member | Own assigned brands under existing feature permissions | No administrative credential writes | No | No | No |
| Organization member with no assignments | None | None | None | No | No |
| Workspace API key | Bound workspace only, existing feature permissions | Only permitted scoped operations | Deny human/team administration by default | No | No |

Add reusable company-member/company-owner guards; use database truth on every request. CRM services continue to scope by authorized workspace, never by organization alone. Verify resource-to-workspace binding for nested IDs, batches, exports, attachments, assistant tools, sockets, scheduled jobs, and public surfaces. Unauthorized company/brand enumeration returns 404; known context but insufficient role returns 403. API-key principals cannot call company management/billing even if their underlying user owns it. Company owner cannot supply another company's workspace ID.

### Invitations

Keep existing workspace invites as single-brand grants, adapting guards and acceptance to also establish organization association without widening access. Proposed owner-only organization invite carries a fixed explicit set of workspace IDs and roles (or use separate single-brand invites initially if approved). Every target must belong to that organization; admin inviters cannot include sibling brands or grant company ownership/billing privileges.

Acceptance transaction locks invitation, checks pending/expiry, authenticated normalized email, active organization/brands, inviter's current authority, and unchanged parent mapping; creates organization association and only specified assignments; marks accepted atomically. Concurrent/replayed acceptance is idempotent for the same user and must not overwrite an existing higher/lower role implicitly. Revoked inviter, archived brand, company reassignment, or revoked membership fails closed. Cancel outstanding affected invites on revocation. Preserve delivery-status semantics and retry-safe outbox/idempotency; mock mail in local tests. Admin listings never return raw tokens. Public preview contains only necessary invitation context, no company roster/billing/integration data.

### Onboarding

After approval, new company signup atomically creates organization, first brand, owner association and assignment; seed existing pipeline/default-agent behavior without inventing new capabilities. Add brand uses explicit organization owner/entitlement checks; never a user's default workspace as company identity. Joining an invite must not provision a new billable company as a side effect. Decide invite-aware signup versus preserving existing personal workspace (decision below); never auto-delete old personal workspaces.

Existing workspace onboarding/import stays explicit `workspace_id`; credential changes and paid provisioning require appropriate brand-admin and company entitlement checks. Deprecated default-target mutations must reject ambiguous multi-brand contexts or be retired with compatibility notice. All fixture runs disable workers and replace Telnyx, Cal.com, FUB, Stripe, email, and AI calls; no live number purchase during migration/testing.

## 6. Company billing and entitlements without Stripe churn

Separate The Tribunal SaaS billing from brand payment collection/deposits/refunds. Do not lift all `integration_type='stripe'` rows into company credentials without classification. Preserve current customers/subscriptions and payment records; no cancel/recreate, customer transfer, account replacement, charges, or subscription changes in backfill.

- Produce a restricted reconciliation manifest: workspace → verified company → verified owner → legacy SaaS integration → customer/provider account/livemode → subscription(s). Preserve encrypted legacy blobs. Inventory uncertain subscription mappings for separately authorized reconciliation; local source alone cannot establish actual provider state.
- Default backfill is **one organization per existing workspace**, even for the same owner/user. Group known brands only using explicit approved company mapping and owner consent. Membership overlap is never sufficient.
- A workspace with unambiguous owner and one billing relationship can attach its existing customer to its new company account without changing Stripe. Two unpaid explicitly related brands can attach to one company after approval. One paid plus one unpaid brand can use the existing paid account only after grouping and entitlement approval.
- Two brands with distinct customers or active subscriptions are a **blocked consolidation case**, not permission to choose one, cancel the other, or charge twice. Keep separate legacy organizations/billing until a separately approved commercial/provider reconciliation plan exists. Repeated customer identifiers across unrelated workspaces are also conflicts, not evidence of common ownership.
- New billing actions require explicit `organization_id`, organization-owner authorization and an allowed plan price. Disable duplicate checkout for an already subscribed/pending company; use durable idempotency. Do not accept arbitrary unapproved price IDs.
- New signed webhook events resolve by unique persisted company/customer/subscription mapping; retain old workspace metadata routing through that verified mapping. Conflicting old/new metadata or unmapped customer fails closed/quarantines for review, never “first match.” Deduplicate event IDs; handle replay, out-of-order state changes, subscription updates/deletion, and failed provider reads without fabricating unsubscribed status.
- Keep SaaS subscription handling distinct from `booking_deposit` and `call_payment_id`/payment-mode handlers already in `billing.py`. Those remain brand-bound.
- Company entitlement resolver gives a minimal brand-safe capability summary; detailed invoices/customer IDs/portal controls remain owner-only. Authorization always precedes entitlement resolution. No union of subscriptions across companies.
- Proposed entitlement basis is organization-level plan/seats/brand allowance, with usage attributed to unchanged workspace IDs. Seat counting, pooled usage, quotas, grace period and cancellation effects require pricing approval; do not create new monetization behavior during migration. Preserve existing access during shadow reconciliation. Any new usage gating needs explicit approval and concurrency/reservation tests before enforcement.

## 7. Provider identity and brand switching

All non-SaaS integration credentials, Cal.com event types, FUB sync identity, Telnyx numbers/messaging profiles, Resend sender identity, voice agent/tool settings and relay device/channel associations stay brand-bound. Organization billing never becomes an integration fallback. If the deployment uses a shared provider account, its credentials are transport configuration, not proof of shared CRM ownership: maintain unique resource-to-workspace routing and require explicit approved brand sender mappings. Never resolve credentials/resources by company or user's first/default brand. Fail closed on missing/ambiguous mappings.

`telnyx_call_handlers.py:54–61` and `telnyx_message_handlers.py:49–56` already derive incoming workspace from phone records (CODE); retain that anchor and test spoofed/ambiguous resource mappings. Audit every provider's current routing, credential fallback, signatures, idempotency, and public URLs before declaring ready. Duplicate provider event IDs must be scoped appropriately by provider account/resource. Async jobs, conversations, WebSockets and assistant actions carry immutable authorized workspace context: switching the operator UI must not retarget ongoing work. No edits to the user's current call-supervisor work in this task.

Frontend keeps `WorkspaceProvider` as brand context and adds an explicit company context derived from server-returned parent identity, not selection inference. Group only permitted brands under their actual companies; no disclosure of unassigned brand names/counts to ordinary members. Display current company and brand, while keeping `workspace_id` for all existing calls. Add brand is owner/capability-controlled; no billing controls for brand admins/members.

Selection rules: stored IDs keyed by authenticated user and validated against the fresh authorized list; stale/revoked selection is cleared with safe fallback, never used to authorize requests. Persist current organization derived from selected brand, not independently inconsistent IDs. Keep existing loading/empty/unavailable/refresh-failure distinctions; a fetch failure is not “no company.” Clear caches on account change and preserve only correctly user-scoped membership data on brand switch. Explicit company billing caches use organization ID; brand caches use workspace ID. Cancel pending queries, reset drafts/mutations/uploads, reconnect scoped subscriptions, and fence late responses by captured workspace ID/selection generation. Require unsaved-work confirmation rather than sending a brand A form after switching to B. Server guards remain decisive if cached membership survives a refresh failure.

## 8. Proposed API and codegen contract

Paths below are proposals, not current routes. Avoid a broad rename from `/workspaces` to `/brands`.

- Keep `/api/v1/workspaces/{workspace_id}/...` and unchanged IDs for CRM APIs. Add `organization_id` to workspace responses and separate `brand_role`, organization role/owner capability; preserve legacy `role` temporarily with clearly documented brand-only meaning.
- `GET /api/v1/organizations`: only user's active companies, minimal names/IDs and own permissions. `GET /organizations/{organization_id}/workspaces`: only authorized brands for teammates; owner roster access explicit.
- `POST /organizations/{organization_id}/workspaces`: owner-only creation, no arbitrary client organization reassignment. Legacy `POST /workspaces` gets explicit standalone-company semantics or rejects ambiguous requests; never select a default company silently.
- Owner-only organization assignment/invitation endpoints validate all target brands belong to path company; workspace endpoints remain single-brand adapters. Membership DTOs separate organization association from workspace grants. Ownership transfer is not a normal role update.
- `GET /organizations/{organization_id}/billing/status`, `POST .../checkout`, `POST .../portal`: explicit company, owner-only financial details/actions. Workspace entitlement summary is separately filtered for permitted users. DTOs carry organization ID, canonical subscription status, computed capabilities and honest unavailable/reconciliation state; no raw secrets.
- Deprecate unscoped `/billing/*` human endpoints; a temporary adapter requires explicit company or an unambiguous owner-authorized company, never default membership. It must enforce the new owner rule before any provider call. Keep signed webhook URL stable with dual legacy/new mapping support.
- Preserve `/auth/me.default_workspace_id` for compatibility; additive organization/context fields do not make JWTs authority snapshots. Contracts define 401/403/404/409/validation and provider-unavailable outcomes.

After future schema/route changes, run `make codegen`, review `backend/openapi.json`, regenerate `frontend/src/lib/api/_generated.ts` (never hand-edit), update hand-written clients/types and `query-keys.ts`, then `make ci.codegen`. Current workspace/billing clients hand-maintain interfaces, so generated drift checks alone do not prove those clients match. Add response/serialization tests and exercise representative URLs with `.ezcoder/eyes/http.sh` against the local fixture server, including wrong-company/member/API-key denials. No contract generation is needed for this docs-only task.

## 9. Dependency-ordered implementation steps (after approval)

1. **Approve policy and inventory.** Resolve decisions below; publish glossary/decision note; inspect remaining auth/provider/entitlement paths. Prepare reviewed explicit organization/owner/billing mapping manifest, ambiguous-case counts, and untouched CRM/Stripe baseline. Gate: no unresolved grouping/owner/billing conflict in cohort.
2. **Build proof fixtures and recovery harness.** Add synthetic company/brand/principal/provider fixtures to existing suites; egress-denied mocks; dedicated disposable Postgres; migration assertion/restore scripts; record schema head and row/FK/integration fingerprints. Gate: fixture safety and restore drill established before data changes.
3. **Expand schema only.** Add organization/membership/billing mapping tables and nullable workspace parent, restrictive FKs, indexes and uniqueness. No CRM rewrites/drops or paid calls. Use migration SQL review and lock/statement timeouts; preserve legacy reads. Gate: clean-install and upgrade fixture parity.
4. **Backfill explicit mappings.** One-company-per-workspace baseline, approved grouping exceptions only. Resumable keyset batches with manifest/checkpoints; per-company transactions and conflict-stop handling. Establish owner associations and explicit assignments without bulk granting teammates. Preserve legacy roles/blobs. Gate: IDs/data/membership/Stripe reconciliation unchanged and ambiguity queue resolved for cohort.
5. **Introduce guarded services/contracts.** Company dependencies, explicit brand creation, role/assignment guards, invitation acceptance transaction, onboarding targeting; repair custom guard/API-key gaps. Regenerate contracts. Gate: permission matrix, race tests and backward-compatible DTO proof.
6. **Shadow then activate billing resolver.** Resolve canonical legacy mappings without provider mutations; compare shadow results. Add owner checks on all old/new entry points before enabling company billing. Mock signed event replay and paid-call-denial tests. Gate: no owner/member authority ambiguity, no duplicate customer/subscription, no payment-flow regression. A commercial consolidation plan is separate.
7. **Integrate frontend context/switching.** Company-grouped permitted-brand list, storage/cache identities, explicit company billing and capability-gated actions, draft/request/socket fencing. Gate: two-brand and cross-company browser fixtures plus account/revocation transitions pass.
8. **Verify provider/runtime isolation.** Test inbound/outbound routing and scheduled/assistant/public operations with mocked providers. Run local API/log probes on changed paths; all tests in readiness matrix must pass. Gate: no stale/default/organization-wide CRM fallback.
9. **Pilot rollout and contract.** Feature-flag one approved synthetic/internal cohort, then selected customer cohorts after backup/restore evidence and separate deployment approval. Observe authorization denials, reconciliation exceptions, isolation canaries and errors without secrets/PII. Validate full backfill before non-null FK/constraint enforcement. Do not drop legacy billing/role columns or compatibility handlers in this rollout; later cleanup needs its own approval and backup.

## 10. Rollout, backups, and rollback requirements

**No database commands were executed for this plan. Backup/PITR configuration and recoverability are unverified.** Before any future command resolve its exact target; unknown is potentially real data. Never default migration/tests to the developer's configured database. `make ci.migrations` targets the configured backend DB, so use only a separately verified disposable target. Do not use `make db.reset` on shared/live data.

For production schema/backfill authorization require: verified backup/PITR point for the actual database; encrypted off-instance backup; protected encryption-key recovery access; object/file recovery coverage; schema revision and restricted mapping manifest; row counts/dry-run affected counts; exact commands and explicit user approval. State and approve RPO/RTO/retention, then restore to a separate destination and time it. Validate representative contacts/conversations/appointments, integration decryption, memberships and Stripe identifier mappings. A local `pg_dump` target existing in Makefile is CODE, not evidence of production recoverability. Its restore target overwrites the configured local DB; never use it against the source as a recovery experiment.

Railway pre-deploy automatically runs Alembic (project configuration); do not publish/apply migration code until the deployment gate is satisfied. Deploy additive schema, compatible backend, verified backfill, then flagged clients/resolvers; only later enforce completeness. Workers must not run against half-resolved company mappings or duplicate background loops. Production inspection should use read-only credentials; write credentials should not be the local shell default.

Rollback before writes: turn flags off and retain additive schema. After assignment/company writes: freeze company management/billing mutations, stop affected jobs, revert to a **permission-safe compatibility release**, not the old unguarded billing handlers. Keep workspace-scoped CRM operation and existing owner checks; restore old assignment semantics only from the reviewed manifest, never fabricate memberships. Preserve new brands as isolated workspaces and new mappings for reconciliation rather than deleting them. Shadow and active billing resolution cannot both write independently. Quarantine uncertain webhook events for deterministic replay after reconciliation; payments must not disappear.

No destructive Alembic downgrade on real data. Prefer forward correction. Point-in-time restore is a last-resort, separately authorized operation into a new destination with reconciliation of post-backup CRM writes and external Stripe/provider events; DB restoration does not undo external charges or subscriptions. Abort rollout on cross-brand access, lost memberships, owner conflicts, mismatched Stripe identity, unexpected zero counts, or corrupted credentials; stop and inspect, do not reseed.

## 11. Local fixture/migration proof and readiness matrix

Build on existing suites: `backend/tests/services/workspaces/test_personal_workspace.py`, `tests/api/test_deps_api_key_workspace.py`, `test_invitations_delivery.py`, `test_realtor_onboarding_workspace_target.py`, `test_billing_api.py`, `test_voice_campaigns_workspace_isolation.py`, `tests/services/onboarding/test_workspace_setup.py`, and `tests/models/test_workspace_integration.py`; frontend `workspace-provider.test.tsx`, `auth-provider.test.tsx`, invite-page/team-invite tests and billing-entry-point tests. Existing mock billing tests do not establish company permissions or real migration integrity.

Synthetic fixture: Company X with legacy Brand A and Brand B (different unchanged UUIDs); Company Y with Brand C; owner X assigned A/B; teammate AB assigned A/B; teammate A assigned A only; admin B assigned B only; consultant assigned A/C; organization member with no brands; former member; API key A. Create distinct canary contacts, conversations, agents, campaigns, opportunities, appointments, phone numbers, settings, encrypted credentials and sender IDs per brand, including matching contact emails/phones across A/B to test local dedupe. Mock legacy SaaS customer/subscription, unpaid second brand, conflicting two-paid brands, duplicated customer and corrupt credentials. No real tokens/customer IDs/customer content.

Migration fixtures cover empty database → head; production-shaped previous revision → expand/backfill/validate; rerun/resume after interruption; concurrent assignment/invitation/owner changes; inactive workspaces, zero/multiple owners, multiple defaults, orphan memberships, pending invites, duplicate provider/customer mappings, and missing owner users. Ambiguity stops without merging/deleting. Compare before/after all workspace IDs, CRM row counts and FK graph, integration encrypted blobs, public slugs, phone IDs and customer/subscription identifiers; only approved organization associations change. Test uniqueness/FK failures and atomic rollback on a separate throwaway DB. Rehearse forward correction and application rollback with new brand/invite writes retained.

All rows below are **required proof, not current passes**:

| Readiness row | Local evidence to gather | Current status |
| --- | --- | --- |
| One login, A/B isolated reads | AB lists/selects both; A contact/conversation/agent/campaign/settings canaries never appear in B list/detail/search/export/assistant responses | CODE foundation; runtime unproven |
| A-only teammate | Only A shown; B URLs/IDs/batches/settings and organization roster rejected, no sibling metadata | Missing organization-aware tests |
| Cross-company consultant | A/C remain in X/Y; cannot see B or administer either company; changing defaults never groups X/Y | Missing |
| Organization owner | Explicit A/B assignments provisioned; controls X billing only; cannot access Y or revoke last owner | Missing; owner policy pending |
| API key A | Deny B even for AB owner; deny company billing/team management; custom invitation/onboarding paths covered | Partial dependency tests exist; gaps require work |
| Settings/integrations | Update A timezone/autonomy/credentials without B changes; wrong-role writes rejected; unreadable credentials fail closed | CODE foundation; runtime unproven |
| Provider identity | Mock inbound A/B SMS/call/booking and outbound sender/agent/FUB/email/relay match correct workspace; replay/unknown mappings cannot retarget | Audit and fixture proof required |
| Invite/revoke races | Exact selected grants only, matching email, expiry/cancel/replay/concurrent accept, revoked inviter/brand; no billing or sibling access | Single-brand tests exist; company proof missing |
| Onboarding | New owner gets company + brand; invite joining grants only targets; A/B setup/import cannot fall back to default; zero provider purchases | Workspace-target tests exist; company flow missing |
| Switch/cache lifecycle | A→B→A with delayed responses, open form/upload/socket/assistant; no A render/send under B; stale storage, account logout/login and revoked assignments covered | Provider tests exist; full boundary proof missing |
| Company billing | A/B selection shows same X account to owner; member/admin denied before mocked SDK call; consultant C never bills X/Y; legacy routes cannot bypass | Missing; current handler authority is inadequate |
| Entitlements | Company grant applies only after brand authorization; missing subscription/error does not create new checkout or widen access; limits concurrent/retry-safe if approved | Policy pending |
| Stripe preservation | Same legacy customer/subscription before/after; no create/cancel/transfer on migration; old metadata/new mapping replay deduped; conflicting paid brands blocked | Missing; no provider state verified |
| CRM payments/public surfaces | Deposit/refund/call payment keep original brand; public offer/form/widget/review assets never reveal sibling/private data | Targeted regression proof required |
| Recovery/data invariants | Restore into separate DB, encrypted integrations decrypt, IDs/FKs/blobs intact; no cascade losses; fail/resume and app rollback preserve writes | Unverified |
| Contract and local runtime | Generated OpenAPI/type parity, handwritten clients, HTTP probe 2xx/4xx bodies, worker logs, local mocked e2e matrix | Not run; no implementation exists |

Future checks, after verifying isolated targets and installed dependencies: targeted existing pytest/Vitest suites first, `make ci.backend`, `make ci.frontend`, `make ci.codegen`, then `make ci.migrations` with an explicitly verified throwaway DB and full fixture assertions. Use existing Playwright e2e when available with providers stubbed. These commands are planned, not executed here; no tests skipped or modified in this task.

## 12. Open decisions requiring approval before implementation

The company/brand direction is already approved; the following details are not:

1. **Historical company/owner mapping:** approve explicit workspace grouping and authoritative owner for each company. Recommended default: one company per workspace; quarantine zero/multiple/conflicting owners, never infer from a shared user.
2. **Owner CRM reach and delegation:** recommended owner receives explicit admin assignment on every company brand; ordinary teammates remain exact-assignment-only. Approve whether owner can be intentionally excluded from a brand. No delegated company billing/admin role or ownership transfer capability initially.
3. **Brand-admin team scope:** recommended preserve own-brand admin/member invites and grants with no company-role elevation; owner manages cross-brand assignment. Approve whether only owner may assign brand admins.
4. **Invitation shape/signup:** approve owner multi-brand invitation versus separate single-brand invites. Recommended invite-aware signup avoids creating a new personal company; preserve all existing personal workspaces, no automatic deletion or grouping.
5. **Legacy brand owners and endpoints:** approve compatibility lifetime and mapping owner→brand admin, plus explicit standalone-company semantics versus deprecation for legacy workspace creation/default-target mutations. No implicit company selection for ambiguous writes.
6. **Billing conflicts/commercial policy:** approve canonical existing SaaS billing mapping and treatment of companies with multiple paid subscriptions. Recommended block grouping until separately approved reconciliation; this plan does not authorize provider mutations.
7. **Entitlements/pricing:** approve seats (recommended unique active company users), included brand count, pooled versus per-brand usage, grandfathering, grace/cancellation behavior. No new pricing or gating until this is settled.
8. **Recovery/deployment gates:** approve production RPO/RTO/retention, who verifies restore/mapping and grants exact-command deployment permission, pilot cohort, and compatibility retirement criteria.

## Completion audit for this planning task

Deliverable is this one proposed plan, not implementation. Required source flows, local decision notes and a steroids working-code reference were inspected. No database/provider commands, migrations, codegen, dependency installation, application implementation or production rollout were performed. Runtime/migration/backup proof remains future work and is explicitly unverified. Only this planning artifact is intended for commit; unrelated call-supervisor changes must remain unstaged and unchanged.
