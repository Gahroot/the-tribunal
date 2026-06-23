---
id: lead-capture
name: Lead Capture & Lead Magnets
tier: A
status: manifest
summary: Public lead-capture forms and gated lead magnets (quizzes, calculators, downloadable PDFs) that create contacts, fire speed-to-lead auto follow-up, and deliver magnet content by email.
owns_paths:
  - backend/app/api/v1/lead_form.py
  - backend/app/api/v1/lead_magnets.py
  - backend/app/services/lead_magnet_delivery.py
  - backend/app/models/lead_magnet.py
  - backend/app/models/lead_magnet_lead.py
  - backend/app/models/lead_source.py
  - scripts/demo/generate_lead_magnet_pdf.py
  - scripts/demo/upload_lead_magnet.py
  - frontend/src/components/lead-magnets/
  - frontend/src/app/lead-magnets/
  - frontend/src/app/p/   # public marketing/landing tree (p/landing, p/reviews/[token]); p/offers/[slug] is co-owned by the offers block
public_api:
  - backend/app/api/v1/lead_form.py::router
  - backend/app/api/v1/lead_magnets.py::router
  - backend/app/services/lead_magnet_delivery.py::deliver_lead_magnet_to_lead
  - backend/app/services/lead_magnet_delivery.py::build_lead_magnet_email_body
  - frontend/src/components/lead-magnets/calculator-runner.tsx
  - frontend/src/components/lead-magnets/quiz-runner.tsx
  - frontend/src/components/lead-magnets/lead-magnet-content.tsx
depends_on: [core, voice, agent-brain, offers, contacts, messaging]
external_integrations: [telnyx, resend]
env_vars:
  - LEAD_FORM_IP_RATE_LIMIT
  - DEMO_FROM_PHONE_NUMBER
  - API_BASE_URL
  - TELNYX_API_KEY
  - TELNYX_CONNECTION_ID
db_tables:
  - backend/app/models/lead_magnet.py::lead_magnets
  - backend/app/models/lead_magnet_lead.py::lead_magnet_leads
  - backend/app/models/lead_source.py::lead_sources
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

## How to Extract

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
