# AI CRM — Comprehensive Refactoring Plan

## Research Summary

Full exploration of `frontend/` (Next.js 16, React Query, Zustand) and `backend/` (FastAPI, SQLAlchemy, 13 background workers) revealed 18 concrete refactoring opportunities across backend and frontend. Below each item is categorised, with root cause, files involved, and a description of the desired outcome.

---

## Backend Refactors

### 1. Duplicate Phone Normalization (backend)
**Files:** `backend/app/services/telephony/telnyx.py:19-44` · `backend/app/utils/phone.py`  
**Issue:** Two separate phone normalization implementations exist: `telnyx.py`'s `normalize_phone_number()` does simple string manipulation without validation; `utils/phone.py` has `normalize_phone_e164()` using the `phonenumbers` library with proper E.164 validation. The `contact_service.py` imports from telnyx.  
**Fix:** Delete the telnyx version, update all callers to import from `app.utils.phone`.

### 2. Workspace Access Pattern Inconsistency (backend)
**Files:** `backend/app/api/v1/contacts.py` (16+ direct calls), `backend/app/api/v1/opportunities.py`, `backend/app/api/v1/dashboard.py`, `backend/app/api/v1/find_leads_ai.py`  
**Issue:** Some endpoints use `workspace: Annotated[Workspace, Depends(get_workspace)]` (proper FastAPI DI), while many others call `await get_workspace(workspace_id, current_user, db)` imperatively mid-function. The DI pattern is correct: it enables proper request scoping and is more testable.  
**Fix:** Standardize all routes to `Depends(get_workspace)`.

### 3. WorkspaceMembership Repeated Queries (backend)
**Files:** `backend/app/api/v1/workspaces.py` (8 instances), `backend/app/api/v1/settings.py` (6 instances), `backend/app/api/v1/integrations.py`  
**Issue:** Instead of using `get_workspace` dep, these files manually query `WorkspaceMembership` inline every time, sometimes adding role checks. Lots of duplicated code with subtle variations.  
**Fix:** Use `get_workspace` dep everywhere. For admin-only routes, add a `get_workspace_admin` dep to `deps.py`.

### 4. Schema Models Defined Inside Route Files (backend)
**Files:** `backend/app/api/v1/contacts.py` — defines `SendMessageToContactRequest`, `MessageResponse`, `ContactIdsResponse`, `AIToggleRequest`, `AIToggleResponse`, `TimelineItem`, `ImportResult`, `CSVPreviewResponse`, `QualifyContactResponse`, `BatchQualifyResponse` (10 inline schemas).  `backend/app/api/v1/automations.py` — defines `AutomationStatsResponse`  
**Issue:** Schemas belong in `app/schemas/`. Having them in the route file prevents reuse and pollutes the router with type definitions.  
**Fix:** Move all inline schemas to the appropriate `app/schemas/*.py` file.

### 5. N+1 Query in `list_workspaces` (backend)
**File:** `backend/app/api/v1/workspaces.py:22-50`  
**Issue:** `list_workspaces` fetches all `WorkspaceMembership` rows then loops and issues a separate `SELECT Workspace WHERE id = ?` for each one.  
**Fix:** Use a JOIN query: `select(WorkspaceMembership, Workspace).join(Workspace)` in one query.

### 6. Paginate/PaginateUnique Duplication (backend)
**File:** `backend/app/db/pagination.py`  
**Issue:** `paginate()` and `paginate_unique()` are 95% identical, only differing by `result.unique()` call. Called in 30+ places across the codebase.  
**Fix:** Merge into one function with `unique: bool = False` parameter.

### 7. `get_current_user` Duplicates Private Helper Logic (backend)
**File:** `backend/app/api/deps.py:23-97`  
**Issue:** `get_current_user` reimplements the same API key and JWT logic that `_user_from_api_key` and `_user_from_jwt` already implement. If logic changes in the private helpers, `get_current_user` won't see the change.  
**Fix:** Refactor `get_current_user` to call `_user_from_api_key` then `_user_from_jwt`, raising `credentials_exception` if both return `None`.

### 8. Inline Imports Inside Functions (backend)
**Files:** `backend/app/workers/base_campaign_worker.py:183-187` (imports `CampaignReportService` inside `_check_completion`), `backend/app/websockets/voice_bridge.py:80-83` (imports `update`, `AsyncSessionLocal` inside `_save_call_duration`)  
**Issue:** Deferred imports inside functions are an anti-pattern used only to break circular imports. The real fix is to restructure the imports at module level.  
**Fix:** Hoist imports to module level; resolve any circular dependency by moving things where they belong.

### 9. Hardcoded DB Pool Size (backend)
**File:** `backend/app/db/session.py:9-15`  
**Issue:** `pool_size=5, max_overflow=10` are hardcoded. In production (Railway), these should be tunable without code changes.  
**Fix:** Add `db_pool_size: int = 5` and `db_max_overflow: int = 10` to `Settings` in `core/config.py`; reference them in `session.py`.

### 10. Voice Campaigns List Not Using Standard Paginator (backend)
**File:** `backend/app/api/v1/voice_campaigns.py:62-92`  
**Issue:** `list_voice_campaigns` returns a raw `list[VoiceCampaignResponse]` without pagination metadata, while every other list endpoint uses the `paginate()` helper and returns `total`, `page`, `pages`. The frontend can't paginate voice campaigns.  
**Fix:** Use `paginate()`, return `PaginatedVoiceCampaigns` with full pagination response.

---

## Frontend Refactors

### 11. localStorage Utility Duplication (frontend)
**Files:** `frontend/src/lib/api.ts:15-41` · `frontend/src/providers/auth-provider.tsx:22-56`  
**Issue:** `api.ts` defines `safeGetItem/safeSetItem/safeRemoveItem` and `auth-provider.tsx` defines `getToken/setToken/setRefreshToken/removeToken` — both wrapping `localStorage` with SSR guard and try/catch. Pure duplication.  
**Fix:** Extract to `frontend/src/lib/utils/storage.ts` as a typed, shared localStorage utility; import from both files.

### 12. API Response `.data` Unwrapping Boilerplate (frontend)
**Files:** Every file in `frontend/src/lib/api/*.ts` (80+ occurrences of `const response = await api.METHOD(url); return response.data`)  
**Issue:** The pattern adds noise and the extra intermediate variable is unnecessary.  
**Fix:** Add thin typed wrappers `apiGet<T>`, `apiPost<T>`, `apiPut<T>`, `apiPatch<T>`, `apiDelete<T>` to `frontend/src/lib/api.ts` that return `response.data` directly; migrate all `lib/api/*.ts` files to use them.

### 13. Agent Type Duplication (frontend)
**Files:** `frontend/src/types/agent.ts` (defines `Agent` with minimal fields) · `frontend/src/lib/api/agents.ts` (defines `AgentResponse` with 40+ fields)  
**Issue:** Two type definitions for the same backend resource. Components import inconsistently from either source.  
**Fix:** Expand `types/agent.ts` to be the canonical type (matching the full `AgentResponse`); re-export as `Agent`; delete `AgentResponse` from `agents.ts`.

### 14. Inconsistent `workspaceId` Pattern in Hooks (frontend)
**Files:** Most hooks in `frontend/src/hooks/` take `workspaceId: string` as a parameter. But `usePromptVersions.ts` calls `useWorkspaceId()` internally, hiding the dependency.  
**Issue:** Inconsistency makes hooks harder to test and compose. The `useWorkspaceId()` internals shouldn't be mixed with data-fetching hooks.  
**Fix:** Standardize all hooks to accept `workspaceId` as a parameter; callers (components/pages) call `useWorkspaceId()` themselves before passing it.

### 15. `contacts-page.tsx` Monolith (frontend)
**File:** `frontend/src/components/contacts/contacts-page.tsx` (29.6 KB, ~750 lines)  
**Issue:** One component handles: filter state, search, pagination, bulk selection, bulk-delete, bulk-status-update, contact card rendering, empty states, skeleton loading, dialogs. This violates SRP and makes the file hard to work with.  
**Fix:** Extract into focused sub-components: `ContactsToolbar`, `ContactCard`, `ContactsBulkActions`, `ContactsEmptyState`. Use the existing `useContactStore` to share state.

### 16. Campaign Wizard Structural Duplication (frontend)
**Files:** `frontend/src/components/campaigns/sms-campaign-wizard.tsx` · `frontend/src/components/campaigns/voice-campaign-wizard.tsx`  
**Issue:** Both wizards have identical `STEPS` type pattern, use the same shared step components (`BasicsStep`, `ContactsStep`, `ScheduleStep`, `ReviewSummaryCard`, `ReviewScheduleCard`), and duplicate the `useWizard`+`WizardContainer` setup. Only the middle steps differ.  
**Fix:** Extract a `BaseCampaignWizardLayout` component that takes `steps` and `children` and wraps `WizardContainer`; reuse across both wizards.

### 17. `useConversations` Not Using `createResourceHooks` (frontend)
**File:** `frontend/src/hooks/useConversations.ts`  
**Issue:** This hook file manually writes `useQuery` and `useMutation` blocks for list, get, sendMessage, toggleAI, assignAgent, clearHistory. The project already has `createResourceHooks` factory that generates exactly this pattern.  
**Fix:** Use `createResourceHooks` for the standard CRUD operations; keep custom hooks for the non-CRUD actions (sendMessage, toggleAI).

### 18. Error Message Extraction Not Shared (frontend)
**File:** `frontend/src/hooks/usePromptVersions.ts:6-13`  
**Issue:** `getErrorMessage()` utility function is defined locally and is likely needed in other hooks that call mutations with error toasts.  
**Fix:** Move to `frontend/src/lib/utils/errors.ts` as `getApiErrorMessage()`; import wherever toast error handling needs it.

---

## Task Execution Template (for each task agent)

Every task agent must follow this process:
1. **Explore** — Read the specific files listed, understand the current pattern
2. **Research** — Use `mcp__grep__searchGitHub` to find real-world working examples of the target pattern
3. **Plan** — Write a brief plan in the task output (which files change, in what order)
4. **Execute** — Make all changes using `edit`/`write`
5. **Verify** — Run `cd frontend && npm run lint && npm run build` (frontend) or `cd backend && uv run ruff check app && uv run mypy app` (backend)
6. **Fix** — Address any lint/type errors before completing
