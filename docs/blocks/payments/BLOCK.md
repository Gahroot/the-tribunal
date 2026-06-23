---
id: payments
name: In-Call Payments & Deposits
tier: B
status: manifest
summary: Stripe-backed in-call payment / deposit collection — creates hosted Checkout Sessions for an amount requested during a call, texts the secure link to the caller, reconciles session status, and notifies operators on payment. Distinct from SaaS subscription billing.
owns_paths:
  - backend/app/services/payments/
  - backend/app/models/call_payment.py
public_api:
  - backend/app/services/payments/call_payment_service.py::create_payment_checkout_session
  - backend/app/services/payments/call_payment_service.py::retrieve_session_status
  - backend/app/services/payments/call_payment_service.py::mark_call_payment_paid
  - backend/app/services/payments/call_payment_service.py::handle_checkout_session_completed
  - backend/app/services/payments/call_payment_service.py::notify_payment_operators
  - backend/app/services/payments/call_payment_service.py::is_payment_configured
  - backend/app/services/payments/call_payment_service.py::PAYMENT_KIND
depends_on: [core]
external_integrations: [stripe]
env_vars:
  - STRIPE_SECRET_KEY
db_tables:
  - backend/app/models/call_payment.py::call_payments
alembic_migrations: shared linear chain — call_payments (20260610_add_call_payments)
workers: []
extraction_effort: low
extraction_notes: Self-contained at the service layer (only `core` imports), but it shares Stripe with the platform billing block — the SaaS-subscription webhook in `backend/app/api/v1/billing.py` routes `checkout.session.completed` events to `handle_checkout_session_completed` by metadata, and the `call_payments` model carries FKs to messages/conversations/contacts/opportunities/agents owned by other blocks.
---

## Overview

Payments owns the **in-call deposit/checkout flow** — money taken during a live call or conversation, separate from the platform's SaaS subscription billing. The `collect_payment` voice tool (owned by agent-brain) never reads raw card numbers over the AI channel; instead it calls `create_payment_checkout_session`, which asks Stripe for a hosted Checkout Session (`payment` mode) for the requested amount and returns a secure link that gets texted to the caller. The service caps per-request amounts (`MIN_PAYMENT_AMOUNT`/`MAX_PAYMENT_AMOUNT`), handles zero-decimal currencies, reconciles session status, marks the `CallPayment` paid, and notifies operators. This block is intentionally **distinct from SaaS subscription billing**, which stays platform-level in `backend/app/api/v1/billing.py`.

## Internal Dependencies

This block has **no sideways block imports** at the service layer — `call_payment_service.py` imports only `app.core.config.settings` and its own `CallPayment` model. The coupling runs the other way (other blocks depend on payments):

- **agent-brain** → payments: `backend/app/services/ai/crm_assistant/_payment_tools.py:38: from app.services.payments import call_payment_service` — the `collect_payment` voice tool drives `is_payment_configured`, `create_payment_checkout_session`, and `PAYMENT_KIND`.
- **billing (platform)** → payments: `backend/app/api/v1/billing.py` routes Stripe `checkout.session.completed` events whose `mode == "payment"` or `metadata.call_payment_id` is set to `call_payment_service.handle_checkout_session_completed`, keeping the in-call path off the SaaS-subscription path.
- **Soft model FKs (not Python imports):** `call_payments` has `ForeignKey`s to `messages`, `conversations`, `contacts`, `opportunities`, and `agents` (plus `workspaces` from `core`). These tables must exist for migrations/integrity even though no service import crosses the boundary.

Core: `app.core.config.settings` (Stripe secret, `FRONTEND_URL` for success/cancel URLs), `app.db.base.Base`, the async DB session.

## Public Surface

- Service functions (no router of its own — invoked by the agent-brain voice tool and the shared billing webhook):
  - `is_payment_configured()` — gate on `STRIPE_SECRET_KEY`.
  - `create_payment_checkout_session(...)` — opens a hosted Checkout Session; raises `stripe.StripeError` for callers to surface.
  - `retrieve_session_status(session_id)` → `SessionStatus`.
  - `mark_call_payment_paid(...)` and `handle_checkout_session_completed(session, db)` — reconcile a completed payment.
  - `notify_payment_operators(db, payment)` — operator notification on payment.
  - `PAYMENT_KIND = "in_call_payment"` — Stripe metadata tag that routes the webhook away from SaaS billing.
- Data: `CallPayment` model + `CallPaymentStatus` enum (`call_payments` table).

## How to Extract

1. Pull `core` only (settings, encryption, DB session).
2. Copy `backend/app/services/payments/` and `backend/app/models/call_payment.py`.
3. No sideways imports to sever — instead provide the inbound callers: wire `handle_checkout_session_completed` into whatever receives Stripe `checkout.session.completed` events, and expose `create_payment_checkout_session`/`is_payment_configured`/`PAYMENT_KIND` to the calling agent/tool layer.
4. Set `STRIPE_SECRET_KEY` (and the shared `FRONTEND_URL` for Checkout success/cancel redirects).
5. Port the `call_payments` table (migration `20260610_add_call_payments`); decide whether to keep the FKs to messages/conversations/contacts/opportunities/agents or relax them to nullable references if those tables don't come along.
6. No workers to register.

## Risks

- **Shared Stripe webhook:** the in-call path is dispatched from the same `checkout.session.completed` handler as SaaS subscriptions, keyed on `mode`/metadata; if the webhook router isn't carried/rewired, paid sessions never reconcile and `CallPayment` rows stay unpaid.
- **FK fan-out:** `call_payments` references five other blocks' tables; extracting payments alone leaves dangling FKs unless they're made nullable or the referenced tables are included.
- **Money safety:** amount guardrails (`MIN/MAX_PAYMENT_AMOUNT`) and zero-decimal currency handling are correctness-critical — preserve them exactly, and keep raw card data off the AI channel (the hosted-Checkout indirection is the safety boundary).
- **Idempotency:** webhook reconciliation should remain idempotent (look up by `stripe_checkout_session_id`) so retried Stripe events don't double-notify operators.
