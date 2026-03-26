# Comprehensive Refactor Plan — AI CRM

## Executive Summary

After thorough exploration of both frontend and backend, I've identified **12 high-leverage refactoring areas** ordered by impact. The codebase is well-structured overall — you have good abstractions like `BaseWorker`, `WorkerRegistry`, `createApiClient`, and `createResourceHooks`. The issues are mostly about consistency, misplaced code, and accumulated cruft.

---

## 1. 🔴 Move Inline Pydantic Schemas Out of Route Files (HIGH IMPACT)

**Problem:** ~65+ Pydantic `BaseModel` classes are defined inline in `backend/app/api/v1/*.py` route files, while a proper `schemas/` directory already exists. This creates a dual schema system — some resources have proper schemas, others have them scattered in routes.

**Affected Files:**
- `api/v1/agents.py` — `AgentCreate`, `AgentUpdate`, `AgentResponse`, `PaginatedAgents`, `EmbedSettings`, `EmbedSettingsResponse`, `EmbedSettingsUpdate` (lines 21-370)
- `api/v1/contacts.py` — `SendMessageToContactRequest`, `MessageResponse`, `ContactIdsResponse`, `BulkDeleteRequest`, `BulkDeleteResponse`, `AIToggleRequest`, `AIToggleResponse`, `TimelineItem`, `ImportResult`, `CSVPreviewResponse`, `QualifyContactResponse`, `BatchQualifyResponse`
- `api/v1/calls.py` — `CallCreate`, `CallResponse`, `PaginatedCalls`
- `api/v1/dashboard.py` — `DashboardStats`, `RecentActivity`, `CampaignStat`, `AgentStat`, `TodayOverview`, `AppointmentStats`, `DashboardResponse`
- `api/v1/campaign_reports.py` — `CampaignReportResponse`, `CampaignReportSummary`, `CampaignReportListResponse`
- `api/v1/appointments.py` — `AppointmentOverallStats`, `AppointmentAgentStat`, `AppointmentCampaignStat`, `AppointmentStatsResponse`
- `api/v1/demo.py` — `DemoCallRequest`, `DemoTextRequest`, `DemoResponse`, `LeadSubmitRequest`, `LeadSubmitResponse`
- `api/v1/embed.py` — `EmbedConfigResponse`, `TokenRequest`, `TokenResponse`, `ChatRequest`, `ChatResponse`, `ToolCallRequest`, `TranscriptRequest`, `EmbedPhoneRequest`
- `api/v1/phone_numbers.py` — `PhoneNumberResponse`, `PaginatedPhoneNumbers`, `PhoneNumberUpdate`, `SearchPhoneNumbersRequest`, `PurchasePhoneNumberRequest`, `PhoneNumberInfoResponse`
- `api/v1/improvement_suggestions.py` — multiple schemas
- `api/v1/automations.py` — `AutomationStatsResponse`
- `api/v1/device_tokens.py` — `RegisterTokenRequest`, `RegisterTokenResponse`
- `api/v1/workspaces.py` — `UpdateMemberRoleRequest`, `MemberResponse`

**Refactor:** Move all schemas to `backend/app/schemas/` in corresponding files. Route files should only import schemas and define route handlers.

**Impact:** Cleaner separation of concerns, easier schema reuse, better API documentation.

---

## 2. 🔴 Extract Business Logic from Route Handlers (HIGH IMPACT)

**Problem:** Many route handlers in `api/v1/` contain raw SQLAlchemy queries and business logic instead of delegating to service layers. The `contacts/` service layer is a good example of the pattern done right, but most other resources don't have services.

**Worst offenders (by file size = complexity in routes):**
- `api/v1/appointments.py` (23.1K) — Raw SQL for CRUD, stats aggregation, Cal.com sync logic inline
- `api/v1/contacts.py` (23.0K) — Mixed: uses service layer but also has inline logic
- `api/v1/dashboard.py` (19.2K) — All stats queries inline with zero service layer
- `api/v1/prompt_versions.py` (22.6K) — Heavy business logic inline
- `api/v1/voice_campaigns.py` (19.3K) — Direct DB queries
- `api/v1/offers.py` (16.3K) — Direct DB queries  
- `api/v1/opportunities.py` (16.8K) — Direct DB queries
- `api/v1/campaigns.py` (15.7K) — Direct DB queries
- `api/v1/agents.py` (15.7K) — Field-by-field Agent construction (lines 242-283)
- `api/v1/improvement_suggestions.py` (15.8K) — AI service calls inline
- `api/v1/integrations.py` (14.2K) — Direct DB queries
- `api/v1/embed.py` (16.6K) — Complex session logic inline

**Refactor:** Create service classes/modules for resources that lack them:
- `services/appointments/` — CRUD + Cal.com sync + stats
- `services/dashboard/` — Stats aggregation + caching
- `services/opportunities/` — Pipeline + opportunity CRUD
- `services/agents/` — Agent CRUD + embed settings
- `services/offers/` — Offer CRUD + lead magnet associations
- `services/integrations/` — Integration management

**Impact:** Testable business logic, thinner route handlers, reusable service methods.

---

## 3. 🔴 Monolithic `types/index.ts` (1135 lines) (HIGH IMPACT)

**Problem:** `frontend/src/types/index.ts` is a single 1135-line file containing every type in the app. It mixes unrelated domains: contacts, campaigns, voice sessions, Cal.com, offers, lead magnets, calculators, quizzes, etc.

**Refactor:** Split into domain-specific type files:
- `types/contact.ts` — Contact, BusinessIntel, EnrichmentStatus, etc.
- `types/conversation.ts` — Message, Conversation, FollowupSettings, TimelineItem
- `types/campaign.ts` — Campaign, CampaignContact, SMSCampaign, VoiceCampaign
- `types/agent.ts` — Agent, ContactAgent
- `types/appointment.ts` — Appointment, CalcomConfig, CalcomBooking, etc.
- `types/offer.ts` — Offer, ValueStackItem, discount/guarantee/urgency types
- `types/lead-magnet.ts` — LeadMagnet, Quiz*, Calculator*, RichTextContent
- `types/opportunity.ts` — Pipeline, PipelineStage, Opportunity, etc.
- `types/voice.ts` — RealtimeSession, RealtimeEvent, etc.
- `types/workspace.ts` — Workspace
- `types/automation.ts` — Automation, AutomationAction
- `types/experiment.ts` — MessageTest, TestVariant, etc.
- `types/index.ts` — Re-export barrel file

**Impact:** Better discoverability, faster IDE performance, easier to find and modify types.

---

## 4. 🟡 Worker Lifecycle Boilerplate in `main.py` (MEDIUM IMPACT)

**Problem:** `main.py` lifespan handler (lines 146-213) manually starts/stops 13 workers with repetitive `await start_X() / log / await stop_X() / log` for each one. Adding a new worker requires editing 4 places (import, start, stop, log).

**Refactor:** Create a worker registry that auto-discovers and manages all workers:

```python
# In workers/__init__.py or workers/registry.py
WORKER_REGISTRIES = [
    campaign_registry, voice_campaign_registry, followup_registry, 
    reminder_registry, message_test_registry, enrichment_registry,
    prompt_stats_registry, prompt_improvement_registry,
    experiment_evaluation_registry, automation_registry,
    noshow_reengagement_registry, never_booked_registry,
    voice_campaign_registry,
]

async def start_all_workers():
    for registry in WORKER_REGISTRIES:
        await registry.start()

async def stop_all_workers():
    for registry in reversed(WORKER_REGISTRIES):
        await registry.stop()
```

The `reputation_worker` is inconsistent — it uses `reputation_worker.start()/stop()` directly instead of `start_reputation_worker()/stop_reputation_worker()`. Normalize it.

**Impact:** Simpler `main.py`, zero-touch worker registration, fewer merge conflicts.

---

## 5. 🟡 Campaign Type Duplication (MEDIUM IMPACT)

**Problem:** The `Campaign` type in `types/index.ts` (lines 420-476) has backward-compat fields (`type?`, `sent_count?`, `delivered_count?`, `responded_count?`, `failed_count?`, `sms_template?`, `email_subject?`, etc.) alongside the current field names. There are also separate `SMSCampaign` and `VoiceCampaign` types that overlap heavily with `Campaign`.

**Refactor:** 
- Remove backward-compat fields from `Campaign` (or confirm they're unused and delete)
- Consider a discriminated union or shared base for campaign types
- Audit if `SMSCampaign` / `VoiceCampaign` / `Campaign` can be consolidated

---

## 6. 🟡 Agent Create/Update Field-by-Field Copy (MEDIUM IMPACT)

**Problem:** `api/v1/agents.py` lines 242-283 manually copy 30+ fields from `AgentCreate` to `Agent` model one by one. Same pattern in update. This is fragile — adding a field to the schema without updating the route handler silently drops it.

**Refactor:** Use `model_dump()` pattern:
```python
agent = Agent(workspace_id=workspace_id, **agent_in.model_dump())
```

For updates, use `exclude_unset=True`:
```python
for field, value in agent_in.model_dump(exclude_unset=True).items():
    setattr(agent, field, value)
```

This pattern should be audited across all route files.

---

## 7. 🟡 Zustand Store Duplicating React Query State (MEDIUM IMPACT)

**Problem:** `frontend/src/lib/contact-store.ts` maintains local copies of state that React Query already manages — contacts list, pagination, loading states, agents, automations. This creates two sources of truth and sync bugs.

**Refactor:** Keep the contact store only for true client-side UI state:
- `selectedContact` ✅ (UI state)
- `searchQuery`, `statusFilter`, `sortBy`, `filters` ✅ (filter state)
- `contacts`, `contactsTotal`, `contactsTotalPages`, `isLoadingContacts` ❌ (duplicate of React Query)
- `timeline`, `isLoadingTimeline` ❌ (duplicate of React Query via `useContactTimeline`)
- `agents`, `automations`, `contactAgents` ❌ (should be React Query or separate stores)

**Impact:** Single source of truth, fewer bugs, less code.

---

## 8. 🟡 Overly Broad Exception Handling (MEDIUM IMPACT)

**Problem:** 60+ `except Exception` catches across the backend. While some are appropriate (worker loops, WebSocket handlers), many swallow specific errors that should propagate or be handled differently.

**Worst patterns:**
- Workers that catch `Exception` and silently log — may hide critical bugs
- `voice_bridge.py` has 10+ bare `except Exception` catches
- Some catches don't even log the exception

**Refactor:** Audit each `except Exception` and:
1. Replace with specific exception types where possible
2. Ensure all catches at minimum log the exception with `exc_info`
3. Re-raise in cases where the error should not be silently swallowed

---

## 9. 🟡 Empty/Dead Code (MEDIUM IMPACT)

**Problem:**
- `frontend/src/lib/services/` — Empty directory
- `frontend/src/lib/utils/placeholder.ts` — One small utility that probably belongs in a component file or a more general utils file  
- `backend/app/utils/` — Check if anything is here vs unused

**Refactor:** Remove empty directories and consolidate orphaned utilities.

---

## 10. 🟢 Test Coverage Gap (LOW URGENCY, HIGH VALUE)

**Problem:** Only 16 test files exist, all under `tests/services/ai/` and `tests/services/audio/`. Zero tests for:
- API endpoints (0 route tests)
- Services (contacts, campaigns, calendar, conversations, etc.)
- Workers (campaign, followup, reminder, etc.)
- Models
- Schemas

**Refactor:** Prioritize tests for:
1. Critical API endpoints (auth, contacts, campaigns)
2. Business logic services (campaign processing, contact import)
3. Worker behavior
4. Add `conftest.py` fixtures for common test patterns

---

## 11. 🟢 Frontend `useAllContacts` Fetches Every Contact (LOW-MED IMPACT)

**Problem:** `useContacts.ts` lines 43-75 — `useAllContacts` loops through all pages to fetch every contact. For large workspaces, this is an unbounded memory and API load.

**Refactor:** 
- Audit where this is used
- Replace with server-side search/filter endpoints
- If needed for bulk operations, use the existing `useContactIds` endpoint instead

---

## 12. 🟢 Inconsistent Pagination Response Construction (LOW IMPACT)

**Problem:** Every list endpoint manually constructs pagination responses:
```python
return PaginatedX(
    items=[XResponse.model_validate(a) for a in result.items],
    total=result.total,
    page=result.page,
    page_size=result.page_size,
    pages=result.pages,
)
```

This is repeated 30+ times across route files.

**Refactor:** Create a generic paginated response helper:
```python
def to_paginated_response(result: PaginationResult, response_model: type[BaseModel]) -> dict:
    return {
        "items": [response_model.model_validate(item) for item in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "pages": result.pages,
    }
```

Or make `PaginationResult` generic and add a `.to_response()` method.

---

## Execution Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| 1 | Move inline schemas to `schemas/` | Medium | High |
| 2 | Extract business logic to services | High | High |
| 3 | Split `types/index.ts` | Low | High |
| 4 | Worker lifecycle registry | Low | Medium |
| 5 | Agent field-by-field copy fix | Low | Medium |
| 6 | Campaign type cleanup | Low | Medium |
| 7 | Zustand/React Query dedup | Medium | Medium |
| 8 | Exception handling audit | Medium | Medium |
| 9 | Dead code cleanup | Low | Low |
| 10 | Test coverage | High | High (long-term) |
| 11 | `useAllContacts` optimization | Low | Medium |
| 12 | Pagination response helper | Low | Low |

## Recommended Approach

Start with items 3, 4, 5, 6, 9 (low effort, quick wins), then tackle items 1 and 2 (the backbone refactors), then 7 and 8 (medium effort cleanups). Item 10 (tests) should be ongoing.
