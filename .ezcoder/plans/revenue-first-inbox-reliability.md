# Revenue-first improvement: trustworthy daily follow-up

## Recommendation

Preserve the recent UX work. Fix **Today → waiting inbox → review → reply → next lead**, then use the app daily for seven working days before commissioning another redesign.

Working goal: **close more of the operator's existing leads**, not increase SaaS subscriptions. The user did not answer the offered distinction, so this remains an explicit assumption.

Hypothesis: fewer hidden conversations and less searching can help convert existing demand. Neither code review nor popular-app references prove revenue lift. Production usage, lead volume, delivery failures, conversion and collected cash were not inspected.

Approval covers a bounded inbox reliability improvement and daily-use playbook. It does not authorize an app-wide redesign, automatic outreach, production data access, deployment or paid tests.

## Research and limits

Research date: 24 September 2026.

- Inspected git history, Today/inbox services and components, schemas, models, existing tests and revenue calculations. Working tree was initially clean; recheck before implementation.
- Used the connected corpus tool (`steroids`) to read actual source from two already-indexed repositories. No standalone `corpus`, `steroids` or `ezcoder` executable was found on PATH. This was corpus-tool research, not a successful CLI run. No repositories were newly indexed.
- Used authorized Refero MCP for three complete four-step flows and three screen images.
- Findings are **CODE**, not reproduced runtime failures. No application tests, authenticated browser tour or latency measurements were run during planning. Reference images are not this app.
- Python symbol navigation could not resolve the requested definition; exact source inspection was used instead.

## Recent work to preserve

| Commits | Preserve |
| --- | --- |
| `4bc7160`, `7bde174` (22 Sep) | Three-column inbox, AI drafts, saved views, read handling |
| `42e742c`, `0e8956b` (22 Sep) | Guided campaign composer and phone preview |
| `34f3228`, `b48ff97` (23 Sep) | Contact master/detail, inline tasks, money-first opportunity board |
| `2613077`, `21d2d81` (23 Sep) | Appointment confirmation/cancellation recovery and tests |
| `182f1c1` (23 Sep) | Approval cockpit and agent wizard |
| `a382583`, `eff3fd7` (23 Sep) | Setup checklist and standardized empty states |
| `9fb1dec`, `64e4ae6` and related commits | Shared semantic colors and visual cleanup |
| `d64bdc7`, `2ccb667` (23 Sep) | Attempt-level campaign reporting and optional booking deposits |
| `5337f70`, `f4896c3` (24 Sep) | Voice experiments and workspace AI model policies |

Correct inbox behavior without undoing these layouts. Do not redraw every screen to match a different reference.

## Ranked findings

### 1. Reading is mistaken for completing follow-up

`frontend/src/components/conversations/conversations-page.tsx:162-186` computes the waiting count/filter from `unread_count`; lines 242-258 mark opened threads read. A conversation can leave Waiting without receiving a reply.

`backend/app/services/dashboard/today_queue_service.py:92-149` instead defines waiting as active + latest message inbound + AI paused or disabled. Today and inbox disagree about the same work.

Use one server-side definition. Unread remains a separate cue, not a completion state. This predicate describes human-owned replies, not all inbound messages or an AI-failure detector.

### 2. Discovery stops at the first page

`conversations-page.tsx:106-209` fetches only the first 100 conversations and contacts, then searches, filters and counts in React. Hot contact IDs do not overcome the conversation limit. Desktop defaults to `rows[0]` rather than the filtered results (`:212-219`).

Move search/filter/count work into bounded workspace-scoped queries. Add explicit pagination. Default selection must match results; explicit selection should remain visible with an outside-current-view indicator when appropriate.

### 3. Today's reply action loses context

`TodayQueueService._replies_waiting_item` links to Contacts, not a waiting conversation. Link a single item to `/conversations?view=waiting&conversation=<uuid>` and multiple items to `/conversations?view=waiting`. Support contactless threads. No new Today layout is needed.

### 4. Selected-thread identity and read-side effects need boundaries

`frontend/src/components/conversation/conversation-feed.tsx:116-148` independently infers a thread from the first 100 conversations; send uses the contact-level endpoint (`:210-245`). A contact can have multiple threads because conversation uniqueness includes the workspace phone (`backend/app/models/conversation.py:85-88`).

`backend/app/services/conversations/conversation_service.py:91-122` synchronizes campaign assignment/AI settings and can commit during listing. `get_conversation` also synchronizes campaign settings and marks read (`:132-159`). Filtering these reads by AI ownership before synchronization could return inconsistent results.

Add read-only inbox list/detail methods and an explicit mark-read mutation. Leave legacy campaign synchronization unchanged. In inbox mode, pass the selected conversation explicitly into the feed and its actions; preserve contact-page behavior when that input is absent.

## External evidence

### Corpus: two source examples, not a quality survey

1. [DeskcommCRM inbox route](https://github.com/melgarafael/DeskcommCRM/blob/main/app/api/v1/admin/inbox/conversations/route.ts), lines 13-154: bounded validated filters, joined contact context, server pagination and deterministic ordering. Adopt those principles using SQLAlchemy and existing page pagination. Do not copy its cross-tenant admin access, service-role bypass, weak cursor cast or interpolated cursor filters.
2. [Django-CRM account rollups](https://github.com/Django-CRM/Django-CRM/blob/main/backend/accounts/views.py), lines 103-185: shared business definitions, separate booked revenue from cash, and aggregate without multiplying rows across unrelated joins. Apply the shared-definition principle to Today/inbox counts. Do not introduce Django or another revenue ledger.

These are conditional implementation examples, not proof of production quality or improved sales. No new dependency or verbatim source copying is planned; review licensing before any later source adoption.

### Refero: preserve context through a complete task

| Reference | Observed pattern | Apply here |
| --- | --- | --- |
| [Missive flow 6264](https://refero.design/flows/6264), four steps | Save and reopen a named task view | Keep saved views; make their underlying filters accurate |
| [Missive flow 6281](https://refero.design/flows/6281), four steps | Snooze, select time, confirm, undo | Defer snooze until daily use shows deferred work is a bottleneck |
| [Linear flow 6681](https://refero.design/flows/6681), four steps | Filter the list while retaining detail and showing hidden items | Stable selection, visible filters, filtered-empty recovery |
| [Intercom screen 5a1eb15f](https://refero.design/pages/5a1eb15f-2704-4d6e-8779-aecdb079c824), image | Conversation adjacent to customer context | Preserve this app's existing three-column composition |

Also viewed Missive image `d7f90b70-80ae-4e16-8650-ba551ee1664e` and Linear image `c641e200-3c6d-4ee5-b769-4aba73fe115e`. Images were low-resolution: rely on flow details for behavior, not exact spacing/contrast. These are observations, not conversion winners or permission to reproduce branding.

## Backend implementation

### Files and ownership

- New `backend/app/services/conversations/conversation_filters.py`: `human_reply_needed_filters(workspace_id)` shared with Today.
- `backend/app/services/conversations/conversation_service.py`: additive `list_inbox`, `get_inbox_conversation`, `mark_read` methods.
- `backend/app/api/v1/conversations.py`: workspace-member-protected `GET /inbox` before the UUID route; `GET /{conversation_id}/inbox-detail`; `POST /{conversation_id}/read` under the existing router prefix.
- `backend/app/schemas/conversation.py`: compact contact summary, inbox row, pagination/counts, conditional read input.
- `backend/app/services/dashboard/today_queue_service.py`: shared predicate, conversation IDs and direct inbox links.

### Contract

- Validated `view=all|waiting|hot`, trimmed `q` maximum 200 characters, `page >= 1`, default page size 50 and cap 100.
- Preserve current All semantics. Waiting requires active + inbound-last + AI disabled or paused. Hot requires linked contact lead score >=80.
- All/Hot order by latest message descending with nulls last and ID tie-breaker. Waiting orders oldest latest-inbound first with deterministic ID tie-breaker.
- Response includes items, total, page, page_size, pages, and all/waiting/hot counts. Counts use the same search scope before applying the selected built-in view, never just loaded rows.
- Join only list-required contact fields: ID, names, available avatar, status and score. Fetch full contact details only for selection. Counts remain at one row per conversation.
- Search names, normalized/raw conversation phone and latest preview using bound parameters and escaped literal substring matching. Full email uses existing `Contact.email_hash` and `hash_value` normalization, not partial-email matching.
- Inspected `Contact.email`/`phone_number` use `EncryptedString`; `services/_filters/base.py:114-121` directly applies ILIKE and is not a working encrypted-email search solution. Reuse `contacts/contact_filters.py` where applicable, but never decrypt the whole workspace or add plaintext PII columns. Label search as name, number or latest message; document exact-email support and the partial-email tradeoff. Do not expand into fixing unrelated Contacts search.
- Return `needs_human_reply` and `last_message_direction`; React does not infer task state from unread.
- Scope all joins, counts and detail lookups to the authorized workspace. Wrong-workspace IDs use existing not-found behavior. Do not record raw search terms in telemetry.
- Inbox GETs do not sync campaigns, change AI ownership, mark read, call providers or commit. Legacy methods retain their behavior.
- Mark-read accepts the last observed message timestamp and updates only if it still matches, so a later inbound is not erased by a stale request. Handle null/no-message threads without repeated mutation.
- No migration or dependency is planned. Measure queries before suggesting an index; production schema changes are not authorized.

## Frontend implementation

Files:

- `frontend/src/lib/api/conversations.ts`: typed inbox/detail/read methods.
- `frontend/src/lib/query-keys.ts`: workspace/filter/page/selection keys under existing conversation invalidation prefixes.
- `frontend/src/components/conversations/conversations-page.tsx`: server queries, URL selection, pagination and state handling instead of first-100 joins.
- `frontend/src/components/conversations/conversation-list.tsx`: counts, previous/next controls, filtered-empty recovery and selection indication.
- `frontend/src/components/conversation/conversation-feed.tsx`: optional explicit conversation for inbox mode. Use selected identity for draft, send, AI assignment/toggle and history controls; retain contact-page fallback and existing contact-wide timeline presentation. Show the selected sending line; inbox replies use its provider-aware conversation endpoint, not an arbitrary default number.
- `frontend/src/components/conversations/contactless-thread.tsx`: retain exact-ID behavior; key by workspace/conversation and align stale-request handling/invalidation.
- `frontend/src/hooks/useConversations.ts`: reuse conversation-scoped mutations and invalidate Today when reply/AI state changes affect waiting work.
- `backend/openapi.json`, `frontend/src/lib/api/_generated.ts`: regenerate with `make codegen`, never hand-edit.

Behavior:

- Validate URL `view` and `conversation`; support Back/Forward. Search text stays out of the browser address bar.
- Deep links resolve independently of the current page; inaccessible selection shows recovery, never silently substitutes another thread.
- Desktop defaults to first visible result; mobile starts at the list unless selected/deep-linked. Explicit selection survives polling and filters, with clear outside-filter indication.
- After send, keep the thread open and offer the next waiting item. No forced navigation or automatic sending.
- Debounce search with existing patterns, reset page when filters change, bound page size, disable background polling and ignore stale workspace/query responses.
- Preserve saved-view format/storage. Remove the need to fetch every hot-contact ID for inbox filtering.
- Read clears the unread badge only. Actual reply/AI state changes refresh Today and counts; draft generation does not complete work.
- Failed sends preserve draft text. Guard switching away from unsent work; do not persist message bodies in browser storage. Late draft/send results cannot overwrite a different thread or newer edit. Pending and error states remain visible.
- Preserve human review before AI-text send and existing messaging controls. Test only with isolated fixtures/fake provider boundaries, never real recipients or paid model calls.

## Design direction

Surface: data-dense operator app. Audience: busy operators handling urgent replies on desktop/mobile. Single job: find the next genuinely unanswered human-owned thread and act without searching elsewhere.

Thesis: **retain the three-column UI; make state and actions truthful.** Waiting count and oldest work first, customer/AI context second, reply as the primary action.

Reuse existing ConversationList, ConversationFeed, MessageComposer, context panel, PageState components, Button, Sheet, Lucide icons, semantic tokens and query presets. Document evidence/states in new `frontend/src/components/conversations/DESIGN.md` during implementation.

Verify loading, global/filtered empty, retry, inaccessible selection, pending/failed/successful send, mobile list/detail/back, keyboard focus and screen-reader status. Test narrow/intermediate/desktop layouts, zoom/reflow, reduced motion, long content and contrast. Do not claim legal or WCAG conformance from automated checks alone.

## Verification

Before behavior changes, reproduce the waiting/unread mismatch and page limit using synthetic >100-conversation fixtures. Include read-but-unanswered, outbound-last, AI-enabled/paused/disabled, archived/blocked, contactless, two lines for one contact, and a second workspace. Record request counts and list/search latency on the same data before/after.

Backend:

- Extend `backend/tests/services/dashboard/test_today_queue_service.py` for shared meaning and correct links.
- Add `backend/tests/services/conversations/test_inbox_service.py`: database-backed predicates, search, counts, sort/page boundaries, selected lookup, no read-side mutations and conditional read race.
- Add `backend/tests/api/v1/test_conversation_inbox.py` following existing API fixtures: membership, wrong-workspace denial, validation and serialization.
- Exercise actual local endpoints with `.ezcoder/eyes/http.sh`, inspecting redacted response artifacts. Never treat legacy conversation GETs as side-effect-free production probes.

Frontend:

- Add `frontend/src/components/conversations/conversations-page.test.tsx`, `conversation-list.test.tsx`, and `frontend/src/components/conversation/conversation-feed.test.tsx` using existing Vitest/Testing Library.
- Cover viewed-but-unreplied persistence, page-2 search, counts, links outside page 1, URL/workspace switching, selected sending line, failed-send retention and late AI responses.
- Add `frontend/e2e/inbox-followup.spec.ts`: Today → waiting inbox → selected thread → read → controlled reply → updated queue on desktop/mobile, plus keyboard operation.
- Existing Playwright helpers skip without test credentials. A skipped run is not proof. Obtain a local seeded account if needed; do not request production credentials or send real messages.
- Capture actual rendered screenshots and interaction evidence. Existing smoke-tour screenshot infrastructure was inspected but not run during planning. Report unavailable checks honestly.
- Run targeted suites, `make ci.backend`, `make ci.frontend`, `make codegen`, then `make ci.codegen`, plus the new E2E case with prerequisites met. Re-read formatter/codegen mutations and inspect the final diff.

Acceptance: Today/inbox agree for unchanged data; opening a thread does not complete work or change AI ownership; eligible rows beyond 100 are searchable/reachable; actions target the selected workspace/thread/line; failures preserve user work; no unauthorized data is returned. Report measured request/latency changes rather than saying merely “faster.”

## Daily-use evaluation and deferred work

Create `docs/revenue-first-daily-use.md` with a seven-working-day checklist and aggregate-results template. No new analytics service or customer-message logging.

Each day: open Today, handle genuine waiting replies and approvals, follow through on appointments, and record opportunity outcomes. Compare starting/ending reply backlog, age of latest unanswered inbound, sampled time to locate/reply, bookings and won value. Record inbound volume so quiet days are not mistaken for progress. Existing `first_response_seconds` measures first response, not recurring follow-up latency.

`DashboardService.get_revenue_stats` already reports pipeline, won value, bookings and estimated AI cost. `ScorecardService.aggregate_scorecard` derives revenue/deposit-like totals from opportunities, not proof of collected Stripe cash. Keep those meanings separate; do not build another ledger in this slice.

Seven days can expose friction and usage, not prove causal revenue lift, especially for long sales cycles. Delivery includes the tested code and playbook, not a claim that the future observation period has already happened.

Defer no-show recovery, snooze persistence, new acquisition automation, SaaS activation redesign and broad runtime optimization until usage or measurements justify the next target.

## Steps

1. Recheck repository state and local verification prerequisites, reproduce waiting/page-limit defects with synthetic fixtures, and record baseline requests and latency without contacting real people.
2. Add the shared human-reply predicate and database-backed regression cases, then implement read-only inbox list/detail queries and conditional mark-read behavior.
3. Expose and test validated workspace-scoped inbox endpoints and schemas, including counts, compact contact summaries, tenant isolation and no read-side AI changes.
4. Update Today to use the shared predicate and inbox links, regenerate API contracts, and add typed frontend methods and query-key builders.
5. Connect the existing inbox to server search, counts and pagination, including URL selection, saved views, filtered/default selection, mobile navigation and recovery states.
6. Pass explicit conversation identity into linked-thread actions, retain contact-page compatibility, protect drafts from switches/stale results, and refresh Today/inbox after relevant mutations.
7. Add frontend interaction and Playwright regression coverage, document the retained inbox design, and verify the local API and rendered desktop/mobile flow.
8. Write the seven-day daily-use checklist, run affected CI/codegen checks, compare measurements with baseline, and review the final diff with implemented/tested/unverified results separated.
