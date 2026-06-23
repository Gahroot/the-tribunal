---
id: contacts
name: Contacts, Segments & Tags
tier: C
status: manifest
summary: The contact/lead system of record — CRUD, import, encrypted phone/email lookup, timelines, engagement scoring, AI qualification state, plus rule-based segments and tags. Its contact_filters engine is the shared audience-selection primitive used across campaigns and automations.
owns_paths:
  - backend/app/services/contacts/
  - backend/app/services/segments/
  - backend/app/services/tags/
  - backend/app/api/v1/contacts.py
  - backend/app/api/v1/segments.py
  - backend/app/api/v1/tags.py
  - backend/app/models/contact.py
  - backend/app/models/segment.py
  - backend/app/models/tag.py
  - frontend/src/components/contacts/
  - frontend/src/components/segments/
  - frontend/src/components/tags/
  - frontend/src/components/filters/
public_api:
  - backend/app/api/v1/contacts.py::router
  - backend/app/api/v1/segments.py::router
  - backend/app/api/v1/tags.py::router
  - backend/app/services/contacts/__init__.py::ContactService
  - backend/app/services/contacts/contact_filters.py::apply_contact_filters
  - backend/app/services/contacts/engagement_score.py::record_engagement
  - backend/app/services/segments/segment_service.py::SegmentService
  - backend/app/services/tags/__init__.py::TagService
  - frontend/src/components/contacts/contact-card.tsx
  - frontend/src/components/filters/contact-filter-builder.tsx
  - frontend/src/components/segments/segment-picker.tsx
  - frontend/src/components/tags/tag-picker.tsx
depends_on: [core, agent-brain, voice]
external_integrations: []
env_vars: []
db_tables:
  - backend/app/models/contact.py::contacts
  - backend/app/models/segment.py::segments
  - backend/app/models/tag.py::tags
alembic_migrations: shared linear chain — contacts + tags (e6c0ca7dd25e_initial_schema), segments (z8a9b0c1d2e3_add_segments); contact columns extended across later revisions.
workers: []
extraction_effort: medium
extraction_notes: Contacts is a near-leaf domain but has two sideways imports: the contacts router calls agent-brain's qualification (analyze_and_qualify_contact / batch_analyze_contacts) and contact_service pulls voice's text_provider to resolve the SMS sender. Conversely many blocks import contacts' apply_contact_filters and TagService and the Contact model directly, so it is widely depended-upon — the entanglement is mostly inbound.
---

## Overview

Contacts is the system of record for people in a workspace — leads, prospects, customers. It owns contact CRUD, CSV/bulk import, the encrypted phone/email lookup path (via core's `hash_phone`/`hash_value`), per-contact timelines, engagement scoring, and the AI qualification/state machine fields. Alongside it sit **segments** (saved, rule-based contact lists) and **tags** (labels with picker/management UI). The shared primitive here is `contact_filters.py::apply_contact_filters` — the rule-based audience-selection engine that campaigns, outbound missions, and automations all reuse to choose who to target (called out as a shared local primitive in CLAUDE.md).

## Internal Dependencies

Sideways block imports to sever (non-`core`, from `docs/blocks/coupling-report.json`):

- `backend/app/api/v1/contacts.py:505,602: from app.services.ai.qualification import analyze_and_qualify_contact, batch_analyze_contacts` → **agent-brain** — running AI qualification on a contact (or a batch) from the contacts router.
- `backend/app/services/contacts/contact_service.py:34: from app.services.telephony.text_provider import get_text_message_provider` → **voice** — resolving the workspace SMS sender/transport when creating or messaging a contact.

Core: `app.api.deps` (`DB`, `CurrentUser`, `TransactionalDB`, `get_workspace`), `app.db.scope` (`get_workspace_owned`, `select_workspace_owned`), `app.db.pagination` (`paginate_rows`, `PaginationResult`, `list_response`), `app.core.encryption` (`hash_phone`, `hash_value`).

## Public Surface

- Authenticated REST routes: `/api/v1/workspaces/{workspace_id}/contacts` (`contacts.router`), `/segments` (`segments.router`), `/tags` (`tags.router`).
- Services consumed by other blocks: `ContactService` (imported by hitl's approval gate), `apply_contact_filters` (imported by messaging's growth workflow and automations for audience selection), `TagService` (imported by messaging's promotion flow and the automation worker), `record_engagement` (imported by voice's inbound/outbound telephony), and the `Contact` model itself (read directly by several blocks).
- Frontend: `contacts/` (cards, sidebar, bulk actions, form dialogs, import), `segments/` (picker, save dialog, page), `tags/` (badge, picker, management), `filters/` (contact filter builder, filter chips).

## How to Extract

1. Pull `core` plus `agent-brain` (for qualification) and `voice` (for the SMS transport) transitively. If the new project doesn't need AI qualification or SMS, both imports can be stubbed and the closure shrinks to just `core`.
2. Copy `owns_paths` (contacts/segments/tags services, three routers, three model files, four frontend trees).
3. Sever the two sideways imports: inject a qualification port (agent-brain) into the contacts router and a transport/sender-resolution port (voice) into `contact_service`.
4. Mount the three routers; export `ContactService`, `apply_contact_filters`, `TagService`, and `record_engagement` for the many blocks that depend on them.
5. No block-specific env vars; rely on core boot vars (`ENCRYPTION_KEY` is required for the encrypted lookup columns).
6. Port `contacts`, `segments`, `tags` and their creating revisions; mind that contact columns are extended across later revisions.
7. No workers to register.

## Risks

- **Widely depended-upon:** more blocks import *into* contacts than contacts imports out — removing or renaming `apply_contact_filters`, `TagService`, `ContactService`, `record_engagement`, or the `Contact` model breaks messaging, automations, hitl, and voice.
- **Encrypted lookup correctness:** phone/email lookups depend on core's `hash_phone`/`hash_value` and a stable `ENCRYPTION_KEY`; a key change makes existing lookup hashes unmatchable.
- **Filter-engine contract:** `contact_filters` is a shared primitive with an implicit rule schema; changing its semantics during extraction silently changes who campaigns/automations target.
- **Qualification optionality:** the agent-brain qualification import is on the contacts router; if not pulled, gate those endpoints behind a feature flag rather than leaving a hard import error.
- **PII / tenancy:** contacts hold live customer PII; every query must stay behind `apply_workspace_scope`/`get_workspace_owned` to avoid cross-workspace leakage.
