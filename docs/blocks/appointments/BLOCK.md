---
id: appointments
name: Appointments & Calendar
tier: B
status: manifest
summary: Books, reschedules, and tracks appointments per workspace via Cal.com; assigns bookable staff, resolves availability, sends SMS reminders, and runs no-show / never-booked re-engagement.
owns_paths:
  - backend/app/services/appointments/
  - backend/app/services/calendar/
  - backend/app/api/v1/appointments.py
  - backend/app/api/v1/bookable_staff.py
  - backend/app/workers/reminder_worker.py
  - backend/app/workers/never_booked_worker.py
  - backend/app/workers/noshow_reengagement_worker.py
  - backend/app/models/appointment.py
  - backend/app/models/bookable_staff.py
  - frontend/src/components/calendar/
  - frontend/src/app/calendar/
public_api:
  - backend/app/api/v1/appointments.py::router
  - backend/app/api/v1/bookable_staff.py::router
  - backend/app/services/appointments/appointment_service.py::AppointmentService
  - backend/app/services/calendar/booking.py::BookingService
  - backend/app/services/calendar/calcom.py::CalComService
  - backend/app/services/calendar/bookable_staff_service.py::BookableStaffService
  - backend/app/services/calendar/reminder_service.py::resolve_from_number
  - frontend/src/components/calendar/calendar-page.tsx
  - frontend/src/components/calendar/new-appointment-dialog.tsx
  - frontend/src/components/calendar/appointment-actions.tsx
depends_on: [core, contacts, messaging, voice, compliance, reviews]
external_integrations: [cal.com, telnyx]
env_vars:
  - CALCOM_API_KEY
db_tables:
  - backend/app/models/appointment.py::appointments
  - backend/app/models/bookable_staff.py::bookable_staff
alembic_migrations: shared linear chain — appointments (e6c0ca7dd25e_initial_schema), bookable_staff (20260611_bookable_staff)
workers:
  - backend/app/workers/reminder_worker.py
  - backend/app/workers/never_booked_worker.py
  - backend/app/workers/noshow_reengagement_worker.py
extraction_effort: medium
extraction_notes: SMS reminders depend on voice's TelnyxSMSService and compliance's OptOutManager; the appointment service imports the Campaign model (messaging) and Contact model (contacts) directly, and completing an appointment calls reviews' ReviewService — creating an appointments↔reviews cycle (reviews also depends on appointments' resolve_from_number).
---

## Overview

Appointments turns conversations into booked time. It integrates with Cal.com (`calcom.py`) to read availability and create/cancel bookings, assigns the right bookable staff member (`staff_assignment.py`, `bookable_staff_service.py`), and persists appointments per workspace. The reminder service sends SMS reminders and resolves the workspace's outbound sending number; background workers chase no-shows (`noshow_reengagement_worker`) and contacts who never booked (`never_booked_worker`). On completion it can trigger a review request through the reviews block.

## Internal Dependencies

Sideways block imports to sever (non-`core`, from `docs/blocks/coupling-report.json` + source):

- `backend/app/services/calendar/reminder_service.py:27 & workers/reminder_worker.py:37: from app.services.telephony.telnyx import TelnyxSMSService` → **voice** — sends appointment reminder SMS.
- `backend/app/services/calendar/reminder_service.py:26 & workers/reminder_worker.py:36: from app.services.rate_limiting.opt_out_manager import OptOutManager` → **compliance** — opt-out enforcement before reminders.
- `backend/app/services/appointments/appointment_service.py:205: from app.services.reviews import ReviewService` → **reviews** — kicks off a review request when an appointment completes (appointments↔reviews cycle; reviews in turn imports `resolve_from_number` from this block).
- `backend/app/services/appointments/appointment_service.py:16: from app.models.campaign import Campaign` → **messaging** — links/looks up the originating campaign for an appointment.
- `backend/app/services/appointments/appointment_service.py:17 & reminder_service.py:21 & workers/{reminder,never_booked,noshow_reengagement}_worker.py: from app.models.contact import Contact` → **contacts** — the contact being booked / reminded / re-engaged.

Core: `app.api.deps`, `app.db.scope`, `app.db.pagination`, `app.core.config.settings`, `app.core.encryption` (Cal.com credentials), `app.services.idempotency`, `app.workers.base`/`retryable`, `app.db.session.AsyncSessionLocal`.

## Public Surface

- Authenticated REST routes: `/api/v1/workspaces/{workspace_id}/appointments` (`appointments.router`) and `/api/v1/workspaces/{workspace_id}/agents/{agent_id}/staff` (`bookable_staff.router`).
- Services: `AppointmentService` (create/reschedule/cancel/complete, availability), `BookingService` (slot resolution + booking), `CalComService` (Cal.com API client with typed errors), `BookableStaffService`, and `resolve_from_number` (consumed by reviews for outbound sending number).
- Frontend: `calendar-page`, `new-appointment-dialog`, `appointment-actions`; `app/calendar/` route.

## How to Extract

1. Pull `core` plus `contacts`, `messaging`, `voice`, `compliance`, and `reviews` transitively. The `reviews` dependency is a cycle (reviews → `resolve_from_number`) — extract appointments + reviews together or break the completion hook into an emitted automation event.
2. Copy `owns_paths` (appointments/calendar services, two routers, three workers, two models, frontend tree + route).
3. Sever sideways imports: vendor/inject `TelnyxSMSService` (voice) and `OptOutManager` (compliance) for reminders; repoint the `Campaign` (messaging) and `Contact` (contacts) model references; replace the `ReviewService` completion call with an event emit if reviews is not carried along.
4. Mount both routers; expose `resolve_from_number` if the new project keeps the reviews block.
5. Set `CALCOM_API_KEY` (Cal.com); Telnyx credentials come with the voice block's SMS service.
6. Port `appointments` (initial schema) + `bookable_staff` (20260611) tables.
7. Register the three workers in the new runner.

## Risks

- **Appointments↔reviews cycle:** completion triggers a review request while reviews depends on `resolve_from_number` here — neither extracts cleanly in isolation.
- **Reminder dependencies:** without voice's `TelnyxSMSService` and compliance's `OptOutManager`, reminders cannot send (or may message opted-out contacts) — booking itself still works.
- **Model-level coupling:** the appointment service imports the `Campaign` and `Contact` models directly; those tables must come along or be replaced with API lookups.
- **Cal.com integration:** availability/booking depends on per-workspace Cal.com credentials (Fernet-encrypted via `core`); Cal.com webhook handling lives under `backend/app/api/webhooks/` and must be wired for booking sync.
- **In-process polling:** reminder/no-show/never-booked workers poll on a schedule; multiple replicas multiply the loops (see CLAUDE.md worker note).
