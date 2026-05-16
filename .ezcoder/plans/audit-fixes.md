# Audit Fixes — Implementation Plan

## Summary

22 verified findings from the 8-agent audit, grouped into 8 parallel sub-agent tasks. Each task is isolated to avoid merge conflicts. All fixes are ordered dependency-first (pyproject.toml changes before code that imports them, etc.).

---

## Task Groupings (Parallel Execution)

### Task 1 — Backend Auth Security
**Files:** `backend/app/core/security.py`, `backend/app/schemas/user.py`, `backend/app/api/v1/auth.py`, `backend/pyproject.toml`

**Fixes:**
1. Replace `python-jose` with `PyJWT` in pyproject.toml + security.py
2. Add `payload.get("type") != "access"` check to `decode_access_token()`
3. Add `Field(..., min_length=8)` to `UserCreate.password`
4. Fix user enumeration in `/register` endpoint (generic error message)

**Real-world patterns to search:**
- `mcp__grep__searchGitHub`: `import jwt` + `from jwt.exceptions import InvalidTokenError` in FastAPI apps
- `mcp__grep__searchGitHub`: `"PyJWT"` in FastAPI pyproject.toml

---

### Task 2 — Backend Security Infrastructure
**Files:** `backend/app/main.py`, `backend/app/core/webhook_security.py`

**Fixes:**
1. Remove `X-XSS-Protection` header, add `Strict-Transport-Security` header in `SecurityHeadersMiddleware`
2. Add global `@app.exception_handler(Exception)` handler using structlog
3. Add timestamp replay-attack check in `validate_calcom_signature()` / `verify_calcom_webhook()` (reject requests older than 5 minutes)
4. Add Redis-backed IP rate limiting to `/api/v1/auth/login`, `/register`, `/refresh` endpoints (follow the pattern used in `demo.py` and `embed.py`)

**Real-world patterns to search:**
- `mcp__grep__searchGitHub`: `exception_handler(Exception)` + `JSONResponse` in FastAPI
- `mcp__grep__searchGitHub`: `Strict-Transport-Security` in FastAPI middleware

---

### Task 3 — WebSocket Infrastructure
**Files:** `backend/app/services/ai/voice_agent_base.py`, `backend/app/services/ai/voice_agent.py`, `backend/app/services/ai/elevenlabs_tts.py`, `backend/app/services/ai/elevenlabs_voice_agent.py`, `backend/app/services/ai/grok/session.py`

**Fixes:**
1. Fix `is_connected()` in `voice_agent_base.py:113` — replace `getattr(self.ws, "open", False)` with `self.ws.state == State.OPEN` using `from websockets.connection import State`
2. Replace bare `import websockets` + `await websockets.connect(...)` with `from websockets.asyncio.client import connect` + `await connect(...)` in all 5 files (voice_agent.py:11,64; elevenlabs_tts.py:15,117; elevenlabs_voice_agent.py:19,239; grok/session.py:17,150)

**Real-world patterns to search:**
- `mcp__grep__searchGitHub`: `from websockets.asyncio.client import connect` usage
- `mcp__grep__searchGitHub`: `websockets.connection import State` + `ws.state == State.OPEN`

---

### Task 4 — Python Async + AI Service Fixes
**Files:** `backend/app/services/email.py`, `backend/app/services/ai/text_response_generator.py`, `backend/app/services/ai/text_prompt_builder.py`, `backend/app/workers/base_campaign_worker.py`

**Fixes:**
1. `email.py:117` — wrap `sg.send(mail)` with `await asyncio.to_thread(sg.send, mail)` + add `import asyncio` at top
2. `text_response_generator.py:223,309,423` — rename `max_tokens` → `max_completion_tokens` in all 3 OpenAI API calls
3. `text_prompt_builder.py:70,132` — replace `datetime.now()` with `datetime.now(UTC)` in both exception fallbacks (already imports `UTC` from datetime at top of file)
4. `base_campaign_worker.py:13,133` — replace `import pytz` + `pytz.timezone(...)` with `from zoneinfo import ZoneInfo` + `ZoneInfo(campaign.timezone or "UTC")`

**Real-world patterns to search:**
- `mcp__grep__searchGitHub`: `asyncio.to_thread` with sendgrid or blocking HTTP clients
- `mcp__grep__searchGitHub`: `max_completion_tokens` in openai chat completions calls
- `mcp__grep__searchGitHub`: `ZoneInfo` replacing `pytz.timezone` in Python 3.12 projects

---

### Task 5 — Python Model Patterns + Dashboard + Pydantic
**Files:** All 19 model files with `(str, Enum)`, `backend/app/api/v1/dashboard.py`, `backend/app/api/v1/contacts.py`

**Fixes:**
1. In all 19 model files — change `class XEnum(str, Enum):` to `class XEnum(StrEnum):` and update imports from `from enum import Enum` to `from enum import StrEnum`. Files:
   - `app/models/appointment.py` — AppointmentStatus
   - `app/models/bandit_decision.py` — DecisionType
   - `app/models/call_feedback.py` — FeedbackSource, ThumbsRating
   - `app/models/call_outcome.py` — OutcomeType, ClassifiedBy
   - `app/models/campaign.py` — CampaignType, CampaignStatus, CampaignContactStatus
   - `app/models/conversation.py` — MessageDirection, MessageStatus, MessageChannel, BounceType
   - `app/models/lead_magnet.py` — LeadMagnetType, DeliveryMethod
   - `app/models/message_test.py` — MessageTestStatus, TestContactStatus
   - `app/models/phone_number.py` — TrustTier, PhoneNumberHealthStatus
2. `dashboard.py:4,22` — replace `import logging; logger = logging.getLogger(__name__)` with `import structlog; logger = structlog.get_logger()`, replace all `logger.debug(f"...")` and `logger.warning(f"...")` f-string calls with structlog structured key-value format
3. `contacts.py` — find `TimelineItem` class with `class Config: from_attributes = True` and replace with `model_config = ConfigDict(from_attributes=True)`, adding `ConfigDict` to the pydantic imports

**Real-world patterns to search:**
- `mcp__grep__searchGitHub`: `from enum import StrEnum` in SQLAlchemy model files
- `mcp__grep__searchGitHub`: `structlog.get_logger` replacing stdlib logging in FastAPI apps
- `mcp__grep__searchGitHub`: `model_config = ConfigDict(from_attributes=True)` in Pydantic v2

---

### Task 6 — Frontend Core React/Next.js Fixes
**Files:** `frontend/src/providers/providers.tsx`, `frontend/src/app/embed/[publicId]/page.tsx`, `frontend/src/app/embed/[publicId]/chat/page.tsx`, `frontend/src/app/experiments/[id]/page.tsx`, `frontend/src/app/p/offers/[slug]/page.tsx`, `frontend/src/app/global-error.tsx` (new), `frontend/src/app/error.tsx` (new)

**Fixes:**
1. `providers.tsx` — move `queryClient` inside component using `useState(() => new QueryClient({...}))` to prevent SSR cache leakage; also use `isServer` pattern from TanStack docs
2. `embed/[publicId]/page.tsx` — wrap `useSearchParams()` caller in a `<Suspense>` boundary. Extract the component that uses `useSearchParams` into a child component, then wrap with `<Suspense fallback={<div>Loading...</div>}>` in the page
3. `embed/[publicId]/chat/page.tsx` — same Suspense fix for `useSearchParams()`
4. `experiments/[id]/page.tsx` — remove `useParams()` import, convert to `params: Promise<{ id: string }>` prop + `const { id } = use(params)` (follow the same pattern as `contacts/[id]/page.tsx`)
5. `p/offers/[slug]/page.tsx` — same fix: remove `useParams()`, use `params: Promise<{ slug: string }>` prop + `use(params)`
6. Create `frontend/src/app/global-error.tsx` — Next.js 15 global error boundary with `"use client"` directive, `error` and `reset` props, proper styling matching existing UI
7. Create `frontend/src/app/error.tsx` — same pattern for route-level errors

**Real-world patterns to search:**
- `mcp__grep__searchGitHub`: `useState(() => new QueryClient` + `isServer` in Next.js App Router providers
- `mcp__grep__searchGitHub`: `useSearchParams` + `Suspense` wrapper in Next.js 15 pages
- `mcp__grep__searchGitHub`: `global-error.tsx` pattern in Next.js 15 App Router

---

### Task 7 — Frontend onError + TanStack Query Patterns
**Files:** `frontend/src/hooks/usePromptVersions.ts`, `frontend/src/components/agents/ab-test-dashboard.tsx`, `frontend/src/components/agents/prompt-version-history.tsx`, `frontend/src/components/agents/agents-list.tsx`, `frontend/src/components/campaigns/campaign-detail.tsx`, `frontend/src/components/campaigns/campaigns-list.tsx`, `frontend/src/components/conversation/conversation-feed.tsx`, `frontend/src/components/experiments/experiments-list.tsx`, `frontend/src/components/experiments/load-template-dialog.tsx`, `frontend/src/components/experiments/save-template-dialog.tsx`, `frontend/src/components/experiments/test-analytics.tsx`, `frontend/src/components/suggestions/experiment-dashboard.tsx`, `frontend/src/components/suggestions/suggestions-queue.tsx`, `frontend/src/components/settings/team-settings-tab.tsx`, `frontend/src/hooks/useInfiniteContacts.ts`, `frontend/src/components/calls/calls-list.tsx`, `frontend/src/components/ui/error-boundary.tsx`

**Fixes:**
1. All `onError: () => toast.error(...)` callbacks that discard the error — update signature to `onError: (err: Error) => toast.error(...)` and use `err.message` or extract from axios error response detail. Files: usePromptVersions.ts (4), ab-test-dashboard.tsx (4), prompt-version-history.tsx (7), agents-list.tsx (4 with console.error), campaign-detail.tsx (4), campaigns-list.tsx (4), conversation-feed.tsx (3), experiments-list.tsx (4), load-template-dialog.tsx (1), save-template-dialog.tsx (1), test-analytics.tsx (2), experiment-dashboard.tsx (4), suggestions-queue.tsx (2), team-settings-tab.tsx (5 with toast.error)
2. `useInfiniteContacts.ts:70` — remove `= 1` default from `({ pageParam = 1 })` → `({ pageParam })`; `hasNextPage: query.hasNextPage ?? false` → `hasNextPage: query.hasNextPage`
3. `calls-list.tsx:106` — remove `= 1` default: `({ pageParam = 1 })` → `({ pageParam })`
4. `error-boundary.tsx:119-120` — fix misleading "Our team has been notified" text to "Please try again or refresh the page." since no error reporting is wired up

**Helper function for axios errors:**
```typescript
function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "object" && err !== null && "response" in err) {
    const axErr = err as { response?: { data?: { detail?: string } } };
    return axErr.response?.data?.detail ?? fallback;
  }
  return fallback;
}
```

**Real-world patterns to search:**
- `mcp__grep__searchGitHub`: `onError: (err)` + `toast.error` + `err.message` in TanStack Query mutations
- `mcp__grep__searchGitHub`: `pageParam` without default in TanStack Query v5 infinite queries

---

### Task 8 — Backend Tests Cleanup + Rate Limiting Config
**Files:** All test files under `backend/tests/` and `backend/` containing `@pytest.mark.asyncio`, `backend/pyproject.toml`

**Fixes:**
1. Find all `@pytest.mark.asyncio` decorators in Python test files (agent confirmed 22 occurrences in 3 files: `tests/services/ai/ivr/test_gate.py`, `tests/services/ai/ivr/test_transcriber.py`, `tests/services/ai/ivr/test_ivr_test_harness.py`) — remove all 22 `@pytest.mark.asyncio` decorators since `asyncio_mode = "auto"` is set in pyproject.toml
2. Verify `pyproject.toml` still has `asyncio_mode = "auto"` after Task 1's changes to pyproject.toml

**Real-world patterns to search:**
- `mcp__grep__searchGitHub`: `asyncio_mode = "auto"` with pytest-asyncio showing tests without `@pytest.mark.asyncio`

---

## Execution Order (Dependencies)

```
Round 1 (fully parallel):
  Task 1 (auth security)    - pyproject.toml + security.py + user.py + auth.py
  Task 2 (security infra)   - main.py + webhook_security.py
  Task 3 (websockets)       - voice_agent_base.py + voice_agent.py + elevenlabs*.py + grok/session.py
  Task 4 (async/AI)         - email.py + text_response_generator.py + text_prompt_builder.py + base_campaign_worker.py
  Task 5 (models/logging)   - 19 model files + dashboard.py + contacts.py
  Task 6 (frontend core)    - providers.tsx + embed pages + experiments + p/offers + global-error.tsx
  Task 7 (frontend errors)  - all onError callbacks + useInfiniteContacts + calls-list + error-boundary
  Task 8 (tests)            - test files

Round 2 (verification):
  cd backend && uv run ruff check app && uv run mypy app
  cd frontend && npm run lint && npm run build
```

## Notes

- **Task 1 and Task 8** both touch `pyproject.toml` — Task 1 removes `python-jose[cryptography]` and adds `PyJWT[crypto]` from dependencies. Task 8 should NOT touch pyproject.toml (it only removes decorators from test files). They can run in parallel safely.
- **Task 2's rate limiting** — use the same DB-based IP check pattern from `app/api/v1/demo.py:134-166` (check count in DB for recent requests from same IP), not Redis, to avoid adding new dependencies. Auth endpoints already have access to `db: DB` via dependency injection.
- **Task 5's StrEnum migration** — `StrEnum` is in stdlib since Python 3.11. The project requires Python 3.12. No new dependencies needed. SQLAlchemy and Pydantic both support `StrEnum` natively since they just use `str` as the base type.
- **Task 7's error helper** — many `onError` callbacks already correctly receive the error (create-agent-form.tsx:103, embed-agent-dialog.tsx:126, etc.). Only fix the ones that use `() =>` (no params at all). Don't change the ones that already receive the error.
