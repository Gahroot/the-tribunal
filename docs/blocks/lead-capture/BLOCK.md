---
id: lead-capture
name: Lead Capture & Lead Magnets
tier: A
status: extracted
summary: Public lead-capture forms and gated lead magnets (quizzes, calculators, downloadable PDFs) that create contacts, fire speed-to-lead auto follow-up, and deliver magnet content by email.
owns_paths:
  - backend/packages/lead-capture/
  - scripts/demo/generate_lead_magnet_pdf.py
  - scripts/demo/upload_lead_magnet.py
  - frontend/packages/lead-capture/
  - frontend/src/app/lead-magnets/   # thin consumer of @tribunal/lead-capture
public_api:
  - backend/packages/lead-capture/src/tribunal_lead_capture/__init__.py::get_router
  - backend/packages/lead-capture/src/tribunal_lead_capture/__init__.py::get_public_router
  - backend/packages/lead-capture/src/tribunal_lead_capture/service.py::deliver_lead_magnet_to_lead
  - backend/packages/lead-capture/src/tribunal_lead_capture/service.py::build_lead_magnet_email_body
  - backend/packages/lead-capture/src/tribunal_lead_capture/models.py::LeadMagnet
  - backend/packages/lead-capture/src/tribunal_lead_capture/models.py::LeadMagnetLead
  - backend/packages/lead-capture/src/tribunal_lead_capture/models.py::LeadSource
  - frontend/packages/lead-capture/src/index.ts::CalculatorRunner
  - frontend/packages/lead-capture/src/index.ts::QuizRunner
  - frontend/packages/lead-capture/src/index.ts::LeadMagnetContent
depends_on: [core, voice, agent-brain, offers, contacts, messaging]
external_integrations: [telnyx, resend]
env_vars:
  - LEAD_FORM_IP_RATE_LIMIT
  - DEMO_FROM_PHONE_NUMBER
  - API_BASE_URL
  - TELNYX_API_KEY
  - TELNYX_CONNECTION_ID
db_tables:
  - backend/packages/lead-capture/src/tribunal_lead_capture/models.py::lead_magnets
  - backend/packages/lead-capture/src/tribunal_lead_capture/models.py::lead_magnet_leads
  - backend/packages/lead-capture/src/tribunal_lead_capture/models.py::lead_sources
alembic_migrations: shared chain — b1c2d3e4f5a6 (offer builder + lead magnets), d2e3f4g5h6i7 (create lead_sources), j4k5l6m7n8o9 (rich lead-magnet content), 20260521 (outbound missions + lead miner)
workers: []
extraction_effort: high
extraction_notes: Highly entangled — a bidirectional model coupling with the offers block (lead-magnet models import Offer/OfferLeadMagnet while offers imports the lead-magnet models and delivery), plus sideways imports into voice (Telnyx auto-text/call), agent-brain (AI quiz/calculator generators), the shared email/push/sla services, and the shared Contact/Campaign/Conversation models.
---

## Overview

Lead capture is the top of the funnel. Public lead forms (`/api/v1/lead-forms/...`) accept unauthenticated submissions, create or match a `Contact`, record a `LeadSource`, and run a configured action — auto-text, auto-call, or campaign enrollment — under speed-to-lead SLA tracking. Lead magnets are gated value assets (AI-generated quizzes and ROI calculators, plus pre-built downloadable PDFs) that capture a `LeadMagnetLead` and email the content via `deliver_lead_magnet_to_lead`. The frontend owns the magnet builders/runners, the authoring routes under `app/lead-magnets/`, and the public marketing/landing pages under `app/p/`.

## Internal Dependencies

Sideways block imports to sever (from `docs/blocks/coupling-report.json`):

- `backend/app/api/v1/lead_form.py:34: from app.services.telephony.telnyx import TelnyxSMSService` → **voice** — auto-text new leads.
- `backend/app/api/v1/lead_form.py:35: from app.services.telephony.telnyx_voice import TelnyxVoiceService` → **voice** — auto-call new leads.
- `backend/app/api/v1/lead_magnets.py:24: from app.services.ai.lead_magnet_generator import generate_calculator_content, generate_quiz_content` → **agent-brain** — AI generation of magnet content.
- `backend/app/models/lead_magnet.py:26: from app.models.offer_lead_magnet import OfferLeadMagnet` → **offers** — relationship back to offers (bidirectional).
- `backend/app/models/lead_magnet_lead.py:16: from app.models.offer import Offer` → **offers** — magnet leads can reference the offer that captured them (bidirectional).

Shared (unassigned / cross-cutting) imports the inventory does not attribute to a block but that still must travel:

- `backend/app/services/lead_magnet_delivery.py:11: from app.services.email import send_automation_email` → **resend** email send.
- `backend/app/api/v1/lead_form.py:28: from app.services.push_notifications import push_notification_service` — operator new-lead push.
- `backend/app/api/v1/lead_form.py:29: from app.services.sla.speed_to_lead import ...` — speed-to-lead proof/SLA.
- Shared models: `app.models.contact.Contact` (→ **contacts**), `app.models.campaign.CampaignContact` (→ **messaging**, campaign enrollment), `app.models.conversation.Conversation`, `app.models.workspace.*`, `app.models.demo_request.DemoRequest`.

## Public Surface

- Lead-form routes (`lead_form.router`, mounted at `/api/v1/p/leads`): preflight + proof endpoints and `POST` submit (`submit_lead`), origin-validated and IP-rate-limited.
- Lead-magnet routes (`lead_magnets.router`, mounted at `/api/v1/workspaces/{workspace_id}/lead-magnets`): list/create/get/update/delete, `POST` AI generate (quiz/calculator), and download-count increment.
- Services: `deliver_lead_magnet_to_lead(...)` (delivers magnet content by email, marks the `LeadMagnetLead`), `build_lead_magnet_email_body(...)`.
- Frontend: builders/runners (`calculator-builder`, `calculator-runner`, `quiz-builder`, `quiz-runner`, `rich-text-editor`, `lead-magnet-content`), `app/lead-magnets/` authoring, and public `app/p/` pages (landing, offers, reviews entry points).
- Scripts: `scripts/demo/generate_lead_magnet_pdf.py`, `scripts/demo/upload_lead_magnet.py` (build + publish magnet PDFs to `/static`).

## Status: extracted

This block is packaged into mountable workspace members. The backend source no
longer lives in the app tree (`app/api/v1/lead_form.py`, `lead_magnets.py`,
`lead_sources.py`, and `app/services/lead_magnet_delivery.py` were removed); it
moved to **`backend/packages/lead-capture/`** (uv distribution
`tribunal-lead-capture`, importable as `tribunal_lead_capture`). The frontend
lead-magnet builders/runners moved to **`frontend/packages/lead-capture/`** (npm
package `@tribunal/lead-capture`).

### Backend

- `get_router()` mounts the authenticated lead-magnet authoring
  (`/workspaces/{workspace_id}/lead-magnets`) + lead-source config
  (`/workspaces/{workspace_id}/lead-sources`) sub-routers; `get_public_router()`
  mounts the public lead form at `/p/leads` — preserving the exact public URL
  `/api/v1/p/leads/{public_key}` embedded forms post to. Both are wired in
  `app/api/v1/router.py`.
- `deliver_lead_magnet_to_lead` is the block's public service API; the offers
  block calls it on opt-in via `from tribunal_lead_capture import
  deliver_lead_magnet_to_lead` instead of a deep service import.
- The three ORM models live in `tribunal_lead_capture.models`; thin back-compat
  shims remain at `app/models/lead_magnet.py`, `app/models/lead_magnet_lead.py`,
  `app/models/lead_source.py` (and schema shims at `app/schemas/lead_magnet.py`
  / `app/schemas/lead_source.py`) that re-export the classes, so existing
  `from app.models...` / `from app.schemas...` imports keep working and
  `app.db.model_registry` still discovers the tables for Alembic. The owned
  tables' creating revisions stay in the host's shared Alembic chain, so the
  package ships no `migrations/` directory.
- Public lead-magnet PDFs are still served unauthenticated from the host's
  `backend/static/` mount; the two PDF build/publish scripts stay under
  `scripts/demo/` (operator tooling) and are documented in the block README.

### Frontend

- `@tribunal/lead-capture` exports the magnet builders/runners + content viewer.
  Host UI primitives (`@/components/ui/*`), shared utils, and `@/types` resolve
  through the package's `@/*` tsconfig alias back to the host `src/`; the
  lead-magnets API client is injected via the `LeadCaptureAdapterProvider`
  (matching the `@tribunal/reviews` adapter precedent). The app routes under
  `app/lead-magnets/` are thin consumers that supply the adapter and own chrome.

## How to Extract

> Historical guide (the extraction has been performed — see *Status: extracted*).

1. Pull `core` plus `voice`, `agent-brain`, `offers`, `contacts`, and `messaging` transitively. Because offers and lead-capture are mutually dependent, extract them together as a pair.
2. Copy every path in `owns_paths` (backend models/routers/delivery, the two PDF scripts, the three frontend trees).
3. Sever the five sideways block imports and the shared email/push/sla service imports — vendor or re-point them.
4. Carry shared `Contact`, `Campaign`/`CampaignContact`, `Conversation`, `Workspace`, `DemoRequest` models and `app/schemas/lead_source.py`, `app/schemas/lead_magnet.py`, `app/schemas/speed_to_lead.py`.
5. Mount both routers; set `env_vars` (lead-form rate limit, Telnyx, demo-from number, API base).
6. Port the three tables and their migrations; mind that `offers`/`offer_lead_magnets` FKs cross into the offers block.
7. No workers to register.

## Risks

- **Bidirectional offers coupling:** the lead_magnet ↔ offer model relationship is circular; extracting lead-capture without offers (or vice versa) leaves dangling imports and FK references.
- **Public, unauthenticated forms:** `submit_lead` is origin-validated and IP-rate-limited only; dropping `validate_origin`/`LEAD_FORM_IP_RATE_LIMIT` opens spam/PII abuse.
- **Email deliverability:** magnet delivery depends on the shared Resend-backed `send_automation_email`; without it leads are captured but never receive content.
- **Tenancy:** lead forms write `Contact`/`LeadSource` rows scoped by workspace — preserve `apply_workspace_scope` and `hash_phone`/`hash_value` lookup hashing.
