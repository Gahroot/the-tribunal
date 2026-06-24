# tribunal-lead-capture

Extracted package for the **lead-capture** block (lead forms + lead magnets +
delivery).

> Mirrors `docs/blocks/lead-capture/BLOCK.md`.

Lead capture is the top of the funnel. Public lead forms accept unauthenticated
submissions, create/match a `Contact`, record a `LeadSource`, and run a
configured action (auto-text, auto-call, campaign enrollment) under
speed-to-lead SLA tracking. Lead magnets are gated value assets (AI quizzes/ROI
calculators + downloadable PDFs) that capture a `LeadMagnetLead` and email the
content via `deliver_lead_magnet_to_lead`.

## Mount

```python
from fastapi import FastAPI
from tribunal_lead_capture import get_router, get_public_router

app = FastAPI()
app.include_router(get_router(), prefix="/api/v1")
# /api/v1/workspaces/{workspace_id}/lead-magnets  (auth)
# /api/v1/workspaces/{workspace_id}/lead-sources  (auth)
app.include_router(get_public_router(), prefix="/api/v1")
# /api/v1/p/leads/{public_key}  (no auth, origin-validated, IP-rate-limited)
```

The prefixes + tags are baked into the routers, so the host mounts them under
its `/api/v1` API prefix exactly as it did before extraction. Also: import
`tribunal_lead_capture.models` so its tables register in `Base.metadata` (the
host does this via the back-compat shims in `app.models.lead_magnet` /
`app.models.lead_magnet_lead` / `app.models.lead_source`).

**Public URL stability:** the public lead-form path
`/api/v1/p/leads/{public_key}` is baked into embedded website forms. Do not
change the `/p/leads` prefix.

## Contract

| Export | Required | Purpose |
|---|---|---|
| `get_router() -> APIRouter` | yes | authenticated lead-magnet authoring + lead-source config |
| `get_public_router() -> APIRouter` | yes | no-auth public lead form (`/p/leads`) |
| `deliver_lead_magnet_to_lead(...)` | — | public service API: email a captured magnet (called by offers on opt-in) |
| `build_lead_magnet_email_body(...)` | — | public helper to render the magnet email body |
| `tribunal_lead_capture.models` | tables only | `LeadMagnet` / `LeadMagnetLead` / `LeadSource` on the shared `Base` |

This block owns no background workers, so it exposes no `register_workers`.

## Static PDF assets (host dependency)

Pre-built lead-magnet PDFs are served **unauthenticated** from the host's
`backend/static/` mount at `/static/...`. A magnet's `content_url` points there,
and `deliver_lead_magnet_to_lead` emails that link. The host keeps the
`app.mount("/static", StaticFiles(directory=backend/static))` mount intact; only
public marketing collateral (lead-magnet PDFs) belongs there — never customer
files, exports, or PII.

The two operational scripts that build + publish those PDFs stay under the
repo's `scripts/` (they are operator tooling, not part of the mountable runtime):

- `scripts/demo/generate_lead_magnet_pdf.py` — render a magnet PDF with `fpdf`.
- `scripts/demo/upload_lead_magnet.py` — create the `LeadMagnet` row pointing at
  the published `/static` URL (`from app.models.lead_magnet import LeadMagnet`,
  which resolves through the back-compat shim to this block).

## Migrations

The block owns the `lead_magnets`, `lead_magnet_leads`, and `lead_sources`
tables, created by revisions in the host's **shared** Alembic chain
(`backend/alembic/versions/`: `b1c2d3e4f5a6` offer builder + lead magnets,
`d2e3f4g5h6i7` create lead_sources, `j4k5l6m7n8o9` rich lead-magnet content,
`20260521` outbound missions + lead miner). This package therefore ships no
`migrations/` directory.

## Dependencies (cross-block public APIs)

Beyond `app.core_api` (settings, DB session, auth/workspace deps, pagination,
encryption/lookup hashing, idempotency), the block calls these sibling blocks /
shared services directly (resolved against the host while in-repo):

- **voice** — `TelnyxSMSService` (auto-text new leads), `TelnyxVoiceService`
  (auto-call new leads).
- **agent-brain** — `generate_quiz_content` / `generate_calculator_content` (AI
  magnet content generation).
- **offers** — bidirectional model relationship (`LeadMagnet` ↔
  `OfferLeadMagnet`, `LeadMagnetLead.source_offer`), and offers calls
  `deliver_lead_magnet_to_lead` on opt-in.
- **contacts** — `Contact` model (lead → contact creation/match).
- **messaging** — `CampaignContact` model (campaign enrollment action).
- **resend / email** — `app.services.email.send_automation_email` (magnet
  delivery).
- shared: `app.services.push_notifications` (operator new-lead push),
  `app.services.sla.speed_to_lead` + `app.schemas.speed_to_lead` (speed-to-lead
  proof badge), `app.models.conversation` / `app.models.demo_request` /
  `app.models.workspace`, and `app.core.origin_validation` /
  `app.core.rate_limit_helpers` / `app.core.utils` (public-form guards).

## Environment variables

The block reads shared core settings via `app.core_api.settings`:

- `LEAD_FORM_IP_RATE_LIMIT` — max public lead-form submits per IP per hour.
- `DEMO_FROM_PHONE_NUMBER` — default from-number for auto-text / auto-call.
- `API_BASE_URL` — builds the lead-source `endpoint_url` and the auto-call
  webhook URL.
- `TELNYX_API_KEY` / `TELNYX_CONNECTION_ID` — outbound SMS/voice (voice block).

## Core contract

Imports core primitives **only** through `app.core_api` (settings, DB session,
auth/workspace deps, pagination, encryption/lookup hashing, idempotency). Public
lead-form guards (`validate_origin`, `raise_rate_limited`, `get_client_ip`) are
imported from their `app.core.*` modules (not yet on the facade), matching the
extracted `tribunal-widget` precedent. No `os.environ`, no hardcoded secrets.
