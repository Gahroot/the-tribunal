---
id: reviews
name: Reviews & Reputation
tier: A
status: manifest
summary: Requests, collects, and analyzes customer reviews per workspace; auto-sends SMS review requests after appointments, routes positive raters to public review sites, and tracks reputation/sender warming.
owns_paths:
  - backend/app/services/reviews/
  - backend/app/api/v1/reviews.py
  - backend/app/models/review.py
  - backend/app/models/review_request.py
  - backend/app/workers/review_request_worker.py
  - backend/app/workers/reputation_worker.py
  - frontend/src/components/reviews/
  - frontend/src/app/reviews/
public_api:
  - backend/app/api/v1/reviews.py::router
  - backend/app/api/v1/reviews.py::public_router
  - backend/app/services/reviews/review_service.py::ReviewService
  - frontend/src/components/reviews/reviews-page.tsx
  - frontend/src/components/reviews/reputation-overview.tsx
  - frontend/src/components/reviews/send-review-request-dialog.tsx
depends_on: [core, voice, agent-brain, appointments, automations, compliance]
external_integrations: [telnyx]
env_vars: []
db_tables:
  - backend/app/models/review.py::reviews
  - backend/app/models/review_request.py::review_requests
alembic_migrations: shared chain — 7015928a0882 (add reviews and review_requests)
workers:
  - backend/app/workers/review_request_worker.py
  - backend/app/workers/reputation_worker.py
extraction_effort: medium
extraction_notes: Review requests are dispatched as SMS via the voice block's TelnyxSMSService and use appointments' resolve_from_number; the worker layer pulls compliance's ReputationTracker/WarmingScheduler/OptOutManager, AI replies come from agent-brain, and review events are emitted through the core automation bus.
---

## Overview

Reviews turns completed appointments into reputation. Per workspace, operators configure review settings (business name, request template, positive threshold, public Google/Facebook URLs, reply tone). When an appointment completes the block can auto-create a `ReviewRequest` and send it as SMS; the recipient submits a star rating via a public `/p/reviews/{token}` page. High raters are routed to public review sites, low raters into private feedback. The reputation worker tracks sender warming/health, and AI can draft review replies.

## Internal Dependencies

Sideways block imports to sever (from `docs/blocks/coupling-report.json`):

- `backend/app/api/v1/reviews.py:34: from app.services.ai.review_reply_generator import generate_review_reply` → **agent-brain** — AI-drafted review replies.
- `backend/app/services/reviews/review_service.py:58: from app.services.automations.events import EVENT_REVIEW_RECEIVED, EVENT_REVIEW_REQUEST_RESPONSE, emit_automation_event` → **automations** — emits review events on the automation bus (this is the sanctioned cross-block hook, kept rather than severed).
- `backend/app/services/reviews/review_service.py:63: from app.services.calendar.reminder_service import resolve_from_number` → **appointments** — resolves the workspace's outbound sending number.
- `backend/app/services/reviews/review_service.py:65: from app.services.rate_limiting.opt_out_manager import OptOutManager` → **compliance** — honors SMS opt-outs before sending.
- `backend/app/services/reviews/review_service.py:66: from app.services.telephony.telnyx import TelnyxSMSService` → **voice** — sends the review-request SMS.
- `backend/app/workers/reputation_worker.py:9: from app.services.rate_limiting.reputation_tracker import ReputationTracker` → **compliance** — reputation scoring.
- `backend/app/workers/reputation_worker.py:10: from app.services.rate_limiting.warming_scheduler import WarmingScheduler` → **compliance** — number-warming schedule.

Core: `app.api.deps` (DB/CurrentUser/get_workspace), `app.db.pagination.paginate`, `app.db.scope.apply_workspace_scope`, `app.services.idempotency` (outbound + worker retry keys), `app.workers.base` / `app.workers.retryable`, `app.db.session.AsyncSessionLocal`.

## Public Surface

- Authenticated routes (`router`, mounted at `/api/v1/workspaces/{workspace_id}/reviews`): settings get/put, reputation `summary`, review-requests list/create, reviews list/create/get/update, `POST /{review_id}/generate-reply`.
- Public routes (`public_router`, mounted at `/api/v1/p/reviews`): `GET /{token}`, `POST /{token}/rate`, `POST /{token}/feedback` (`get_public_review_request`, `submit_public_rating`, `submit_public_feedback`).
- Service: `ReviewService` — settings management, auto-request on appointment completion, send/dispatch logic, public rating/feedback ingestion, sentiment classification.
- Workers: `review_request_worker` (dispatches due requests), `reputation_worker` (reputation + warming).
- Frontend: `reviews-page`, `reviews-list`, `review-requests-tab`, `reputation-overview`, `send-review-request-dialog`, `star-rating`; `app/reviews/` route. Public submission UI lives in lead-capture's `app/p/reviews/[token]`.

## How to Extract

1. Pull `core` plus `voice`, `agent-brain`, `appointments`, `automations`, and `compliance` transitively.
2. Copy `owns_paths` (service, router, two models, two workers, frontend tree + route).
3. Sever sideways imports: vendor/repoint `TelnyxSMSService`, `resolve_from_number`, `OptOutManager`, `ReputationTracker`, `WarmingScheduler`, and the AI reply generator. Keep `emit_automation_event` if the new project retains the automation bus, else drop the emit calls.
4. Mount `reviews.router`; the public token routes need the `/p/reviews/[token]` page (owned by lead-capture) — carry or re-implement it.
5. No block-specific env vars; relies on shared `FRONTEND_URL` and Telnyx credentials.
6. Port `reviews` + `review_requests` tables (migration 7015928a0882) and register both workers in the new runner.

## Risks

- **SMS dependency:** without the voice block's Telnyx service and appointments' `resolve_from_number`, requests cannot be sent — review *capture* still works via the public link.
- **Opt-out compliance:** dropping `OptOutManager`/reputation warming risks sending to opted-out numbers and harming sender reputation — a regulatory and deliverability hazard.
- **Automation hook:** `review_received`/request-response events feed downstream automations; severing the bus silently breaks those workflows.
- **Public token surface:** rating/feedback endpoints are unauthenticated and keyed by token — preserve token validation when extracting.
