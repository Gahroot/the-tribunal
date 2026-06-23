---
id: offers
name: Offers & Offer Builder
tier: A
status: manifest
summary: A guided builder for irresistible offers (value stack, pricing, guarantee, urgency, attached lead magnets) plus public opt-in offer pages that capture contacts and deliver the bundled lead magnets.
owns_paths:
  - backend/app/services/offers/
  - backend/app/api/v1/offers.py
  - backend/app/models/offer.py
  - backend/app/models/offer_lead_magnet.py
  - frontend/src/components/offers/
  - frontend/src/app/offers/
  - frontend/src/app/p/offers/
public_api:
  - backend/app/api/v1/offers.py::router
  - backend/app/api/v1/offers.py::public_router
  - backend/app/services/offers/prestyj_batch_video_ads.py::format_pack_terms
  - frontend/src/components/offers/offer-builder-wizard.tsx
  - frontend/src/components/offers/ai-offer-writer.tsx
  - frontend/src/components/offers/offer-preview.tsx
depends_on: [core, agent-brain, lead-capture, contacts]
external_integrations: []
env_vars: []
db_tables:
  - backend/app/models/offer.py::offers
  - backend/app/models/offer_lead_magnet.py::offer_lead_magnets
alembic_migrations: shared chain — 03876dc32a6c (add offers table + campaign offer_id), b1c2d3e4f5a6 (offer builder + lead magnets), k5l6m7n8o9p0 (public offer fields), 20260614 (offer ladder strategy metadata)
workers: []
extraction_effort: medium
extraction_notes: Bidirectionally coupled with lead-capture — the offers router imports LeadMagnet/LeadMagnetLead models and calls deliver_lead_magnet_to_lead, while the join model offer_lead_magnets and lead-capture's models reference each other; AI offer copy comes from agent-brain and public opt-in writes a shared Contact.
---

## Overview

Offers packages a workspace's value proposition into a publishable offer: a multi-step builder (basics, value stack, pricing, guarantee, urgency, attached lead magnets, review, publish) backed by `Offer` and the `OfferLeadMagnet` join. AI can draft offer copy. Published offers render at public `/p/offers/[slug]` pages where visitors opt in — creating a `Contact` and delivering each attached lead magnet via the lead-capture delivery service. The `services/offers/` module also holds a static productized-offer pack definition (`prestyj_batch_video_ads`) used for guided pricing.

## Internal Dependencies

Sideways block imports to sever (from `docs/blocks/coupling-report.json`):

- `backend/app/api/v1/offers.py:15: from app.models.lead_magnet import LeadMagnet` → **lead-capture** — attach/list lead magnets on an offer.
- `backend/app/api/v1/offers.py:16: from app.models.lead_magnet_lead import LeadMagnetLead` → **lead-capture** — records magnet deliveries from offer opt-ins.
- `backend/app/api/v1/offers.py:38: from app.services.lead_magnet_delivery import deliver_lead_magnet_to_lead` → **lead-capture** — delivers attached magnets on opt-in.
- `backend/app/api/v1/offers.py:37: from app.services.ai.offer_generator import generate_offer_content` → **agent-brain** — AI offer copywriting.
- `backend/app/models/offer_lead_magnet.py:14: from app.models.lead_magnet import LeadMagnet` → **lead-capture** — join-model relationship (bidirectional with lead-capture's reverse imports).

Shared (unassigned) imports that still travel: `app.models.contact.Contact` (→ **contacts**, written by `submit_offer_optin`), `app.models.workspace.Workspace`, `app.api.crud.get_or_404`, `app.schemas.offer.*`, `app.schemas.lead_magnet.LeadMagnetResponse`. Core: `app.api.deps`, `app.db.pagination.paginate`, `app.db.scope` (`apply_workspace_scope`, `select_workspace_owned`).

## Public Surface

- Authenticated routes (`router`, mounted at `/api/v1/workspaces/{workspace_id}/offers`): `POST` AI generate, list/create/get/update/delete, get-with-lead-magnets, attach/detach/reorder lead magnets.
- Public routes (`public_router`, mounted at `/api/v1/p/offers`): `GET /{slug}` (`get_public_offer`), `POST /{slug}/opt-in` (`submit_offer_optin`).
- Service module: `prestyj_batch_video_ads` pack/pricing helpers (`format_pack_terms`, `format_price`, pack definitions); the offer's own CRUD logic lives in the router.
- Frontend: the `offer-builder-wizard` and its step components (basics/value-stack/pricing/guarantee/urgency/lead-magnets/review/publish), `ai-offer-writer`, `offer-preview`, `lead-magnet-selector`, `value-stack-builder`; `app/offers/` authoring routes and public `app/p/offers/[slug]`.

## How to Extract

1. Pull `core` plus `agent-brain`, `lead-capture`, and `contacts`. Extract offers and lead-capture **together** — they are mutually dependent.
2. Copy `owns_paths` (service module, router, two models, both frontend trees).
3. Sever the agent-brain AI import (vendor/repoint `generate_offer_content`); keep the lead-capture imports intact since that block travels with offers.
4. Carry the shared `Contact`/`Workspace` models, `app/schemas/offer.py`, and `app.api.crud.get_or_404`.
5. Mount `offers.router`; no block-specific env vars.
6. Port `offers` + `offer_lead_magnets` tables and migrations; note the `campaigns.offer_id` FK added by 03876dc32a6c reaches into the messaging block.
7. No workers.

## Risks

- **Circular block coupling:** offers ↔ lead-capture import each other's models and services; treat them as a single extraction unit or the import graph breaks.
- **Public opt-in writes Contacts:** `submit_offer_optin` is unauthenticated and creates contacts + magnet deliveries — preserve workspace scoping and rate/origin protections.
- **Cross-block FK:** `campaigns.offer_id` links offers to the messaging block; dropping messaging leaves a dangling FK.
- **Stripe in copy only:** the `prestyj_batch_video_ads` pack references a Stripe checkout in prompt/instruction text — it is not a live Stripe integration in this block (hence `external_integrations: []`).
