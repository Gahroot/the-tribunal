---
id: compliance
name: Compliance & Rate Limiting
tier: C
status: manifest
summary: The messaging-safety substrate — opt-out enforcement (STOP/global opt-outs), outbound compliance checks, per-number rate limiting, reputation/warming, and bounce classification. A cross-cutting dependency that every voice/messaging send must pass through before dispatch.
owns_paths:
  - backend/app/services/compliance/
  - backend/app/services/rate_limiting/
  - backend/app/models/opt_out.py
public_api:
  - backend/app/services/rate_limiting/opt_out_manager.py::OptOutManager
  - backend/app/services/compliance/outbound_compliance.py::OutboundComplianceService
  - backend/app/services/compliance/outbound_compliance.py::OutboundComplianceRequest
  - backend/app/services/compliance/outbound_compliance.py::OutboundComplianceResult
  - backend/app/services/rate_limiting/rate_limiter.py::RateLimiter
  - backend/app/services/rate_limiting/auth_limiter.py::enforce_change_password_rate_limit
  - backend/app/services/rate_limiting/auth_limiter.py::enforce_ws_ticket_rate_limit
  - backend/app/services/rate_limiting/embed_limiter.py::enforce_embed_rate_limit
  - backend/app/models/opt_out.py::GlobalOptOut
depends_on: [core]
external_integrations: []
env_vars: []
db_tables:
  - backend/app/models/opt_out.py::global_opt_outs
alembic_migrations: shared linear chain — global_opt_outs (20260519_outbound_compliance_controls, extended by f1a2b3c4d5e6_add_sms_compliance_rate_limiting).
workers: []
extraction_effort: low
extraction_notes: Compliance depends only on core (Redis for rate-limit counters, the opt_out model, rate_limit_helpers) and imports no other block — it is a near-clean leaf. The hazard is inbound, not outbound: voice and messaging gate every SMS/voice send on OptOutManager and OutboundComplianceService, so removing or weakening it silently enables unlawful/over-rate sending. Extract it first, before the blocks that depend on it.
---

## Overview

Compliance is the safety gate in front of all outbound communication. It owns opt-out enforcement (`opt_out_manager.py` + the `global_opt_outs` table — honoring STOP keywords and global suppression), the outbound compliance service that vets each send (`compliance/outbound_compliance.py`), and the rate-limiting / sender-reputation stack (`rate_limiting/` — per-number pools, rate limiters, reputation tracking, warming schedules, bounce classification, plus auth/embed/scraping limiters). It is **cross-cutting**: it has almost no product surface of its own, but voice and messaging must call into it before dispatching any SMS or placing any campaign, and the public API/auth layers use its limiters to throttle abuse.

## Internal Dependencies

Sideways block imports to sever (non-`core`, from `docs/blocks/coupling-report.json`):

- **None.** Every import in this block points at `core` only:
  - `backend/app/models/opt_out.py:11: from app.db.base import Base` → core.
  - `backend/app/services/rate_limiting/*.py: from app.db.redis import get_redis` and `from app.core.rate_limit_helpers import raise_rate_limited` → core — Redis-backed counters and the 429 helper.

Compliance is a leaf in the dependency graph: it imports core and is imported by others, never the reverse. This is what makes it cheap to extract and dangerous to omit.

## Public Surface

- Services consumed by other blocks (no router of its own):
  - `OptOutManager` — imported by voice (inbound screening, missed-call textback) and messaging (outbound delivery, reply handler, promotion) to block sends to opted-out numbers.
  - `OutboundComplianceService` / `OutboundComplianceRequest` / `OutboundComplianceResult` — imported by messaging's `outbound/delivery.py` for the pre-send compliance check.
  - `GlobalOptOut` model — read by messaging's reply handler to honor global opt-outs.
  - `RateLimiter` plus the auth/embed limiter functions (`enforce_change_password_rate_limit`, `enforce_ws_ticket_rate_limit`, embed limiter) and scraping/number-pool/reputation/warming helpers — used by auth, embed, and lead-capture surfaces to throttle abuse.

## How to Extract

1. Pull `core` only. Provision Redis (rate-limit and opt-out counters live there).
2. Copy `owns_paths` (compliance + rate_limiting services, the `opt_out` model).
3. No sideways imports to sever — confirm nothing here reaches into another block.
4. Export `OptOutManager`, `OutboundComplianceService` (+ request/result types), `GlobalOptOut`, and the limiter classes for the blocks that gate on them. There is no router to mount.
5. No block-specific env vars; rely on core's `REDIS_URL` and boot vars.
6. Port the `global_opt_outs` table and its creating revisions.
7. No workers to register.
8. Extract this block **first**, before voice/messaging, so their compliance gates resolve.

## Risks

- **Inbound dependency, regulatory stakes:** voice and messaging call `OptOutManager`/`OutboundComplianceService` before every send; dropping or stubbing them risks texting/calling opted-out numbers — a legal (TCPA/STOP) and deliverability hazard, not just a bug.
- **Redis-backed state:** rate-limit counters, reputation, and warming live in Redis; a fresh deployment starts with empty counters, so warming/reputation logic must re-baseline.
- **Shared limiters beyond messaging:** the auth and embed limiter functions throttle auth and public embed surfaces too — extracting compliance without wiring these re-opens abuse vectors on those endpoints.
- **Opt-out table semantics:** `global_opt_outs` is keyed on hashed/normalized identifiers; preserve the normalization so suppression matches across channels.
