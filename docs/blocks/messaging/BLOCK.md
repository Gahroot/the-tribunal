---
id: messaging
name: Messaging & Outbound Campaigns
tier: B
status: manifest
summary: SMS/iMessage campaigns, drip sequences, outbound missions, and the unified outbound delivery pipeline — renders templated messages, enforces compliance, dispatches via Telnyx or the mac-relay (iMessage), tracks delivery/replies, and runs AI fallback drafting.
owns_paths:
  - backend/app/services/messaging/
  - backend/app/services/campaigns/
  - backend/app/services/outbound/
  - backend/app/api/v1/campaigns.py
  - backend/app/api/v1/drip_campaigns.py
  - backend/app/api/v1/outbound_missions.py
  - backend/app/api/v1/message_templates.py
  - backend/app/workers/campaign_worker.py
  - backend/app/workers/drip_campaign_worker.py
  - backend/app/workers/outbound_auto_draft_worker.py
  - backend/app/workers/followup_worker.py
  - backend/app/models/campaign.py
  - backend/app/models/phone_message.py
  - backend/app/models/message_template.py
  - backend/app/models/message_trace.py
  - backend/app/models/outbound_mission.py
  - backend/app/models/outbound_sequence.py
  - backend/app/models/outbound_action_audit_log.py
  - frontend/src/components/campaigns/
public_api:
  - backend/app/api/v1/campaigns.py::router
  - backend/app/api/v1/drip_campaigns.py::router
  - backend/app/api/v1/outbound_missions.py::router
  - backend/app/api/v1/message_templates.py::router
  - backend/app/services/outbound/delivery.py::outbound_delivery_service
  - backend/app/services/outbound/delivery.py::OutboundDeliveryService
  - backend/app/services/outbound/delivery.py::OutboundDeliveryRequest
  - backend/app/services/outbound/mission_service.py::OutboundMissionService
  - backend/app/services/campaigns/reply_handler.py::handle_campaign_reply
  - backend/app/services/campaigns/conversation_syncer.py::CampaignConversationSyncer
  - backend/app/services/campaigns/guarantee_tracker.py::check_guarantee_expiry
  - backend/app/services/messaging/link_shortener.py::shorten_urls_in_text
  - frontend/src/components/campaigns/campaigns-list.tsx
  - frontend/src/components/campaigns/sms-campaign-wizard.tsx
  - frontend/src/components/campaigns/voice-campaign-wizard.tsx
depends_on: [core, contacts, agent-brain, compliance, voice, offers, short-links, hitl]
external_integrations: [telnyx, mac-relay]
env_vars:
  - CAMPAIGN_POLL_INTERVAL
  - TELNYX_API_KEY
  - MAC_RELAY_BASE_URL
  - MAC_RELAY_TOKEN
db_tables:
  - backend/app/models/campaign.py::campaigns
  - backend/app/models/campaign.py::campaign_contacts
  - backend/app/models/phone_message.py::phone_messages
  - backend/app/models/message_template.py::message_templates
  - backend/app/models/message_trace.py::message_traces
  - backend/app/models/outbound_mission.py::outbound_missions
  - backend/app/models/outbound_sequence.py::outbound_sequences
  - backend/app/models/outbound_sequence.py::outbound_sequence_enrollments
  - backend/app/models/outbound_sequence.py::outbound_sequence_step_attempts
  - backend/app/models/outbound_action_audit_log.py::outbound_action_audit_logs
alembic_migrations: shared linear chain — campaigns + campaign_contacts (e6c0ca7dd25e_initial_schema), phone_messages (20260609_add_phone_messages), message_templates (p0q1r2s3t4u5_add_message_templates), message_traces (20260615_message_traces), outbound_missions + outbound_sequences (20260521_add_outbound_missions_and_lead_miner)
workers:
  - backend/app/workers/campaign_worker.py
  - backend/app/workers/drip_campaign_worker.py
  - backend/app/workers/outbound_auto_draft_worker.py
  - backend/app/workers/followup_worker.py
extraction_effort: high
extraction_notes: Messaging and voice form an import cycle — outbound delivery sends through voice's TextMessageProvider/TelnyxSMSService while voice's telephony reuses messaging's link shortener, conversation syncer, and reply handler; also pulls compliance (OutboundComplianceService, OptOutManager, GlobalOptOut), offers (Offer model in renderers/missions), short-links (ShortLink), contacts (contact filters, TagService), agent-brain (AI fallback), and hitl (autonomy mandate). `campaign_worker`/`voice_campaign_worker` share `base_campaign_worker`.
---

## Overview

Messaging is the outbound engine. It owns three related surfaces: **campaigns** (one-shot SMS/voice blasts with offers, guarantees, and AI/SMS fallback), **drip campaigns** (scheduled multi-step sequences), and **outbound missions** (lead-mining / growth-workflow driven outreach with promotion and message tracing). All sends funnel through a single `OutboundDeliveryService` that renders templated copy, applies compliance, and dispatches over Telnyx SMS or the mac-relay iMessage channel. Replies are synced back into conversations and routed to the right campaign or AI handler.

## Internal Dependencies

Sideways block imports to sever (non-`core`, from `docs/blocks/coupling-report.json`):

- `backend/app/services/outbound/delivery.py:27: from app.services.telephony.text_provider import TextMessageProvider, get_text_message_provider` → **voice** — the actual SMS/iMessage transport; this is the messaging→voice half of the cycle.
- `backend/app/services/outbound/delivery.py:20,26: from app.services.compliance.outbound_compliance import OutboundComplianceService... / rate_limiting.opt_out_manager import OptOutManager` → **compliance** — pre-send compliance checks and opt-out enforcement.
- `backend/app/services/campaigns/reply_handler.py:17: from app.models.opt_out import GlobalOptOut` → **compliance** — honors global opt-outs when handling replies.
- `backend/app/services/campaigns/reply_handler.py:20 & ai_fallback.py:14: from app.services.ai.openai_credentials import get_openai_bearer_token` → **agent-brain** — OpenAI auth for AI reply/fallback drafting.
- `backend/app/services/messaging/link_shortener.py:13: from app.models.short_link import ShortLink` → **short-links** — persists shortened links.
- `backend/app/services/campaigns/message_renderer.py:8 & outbound/growth_workflow.py:15 & outbound/mission_service.py:29: from app.models.offer import Offer` → **offers** — renders offer details into messages and targets missions by offer.
- `backend/app/services/outbound/growth_workflow.py:18: from app.services.contacts.contact_filters import apply_contact_filters` → **contacts** — audience selection by contact filters.
- `backend/app/services/outbound/promotion.py:38: from app.services.tags.tag_service import TagService` → **contacts** — tags contacts on promotion/state changes (`promotion.py:37` also pulls `OptOutManager`).
- `backend/app/services/outbound/message_trace.py:27: from app.services.autonomy_mandate import escalation_matches, normalize_autonomy_mandate` → **hitl** — applies the operator autonomy/escalation policy to outbound actions.
- `backend/app/workers/campaign_worker.py: BaseCampaignWorker` (`app/workers/base_campaign_worker.py`) — **shared worker base** also used by voice's `voice_campaign_worker`.

Core: `app.api.deps`, `app.db.scope`, `app.db.pagination`, `app.core.config.settings`, `app.services.idempotency`, `app.workers.base`/`retryable`, `app.db.session.AsyncSessionLocal`.

## Public Surface

- Authenticated REST routes: `/api/v1/workspaces/{workspace_id}/campaigns` (`campaigns.router`), `/drip-campaigns` (`drip_campaigns.router`), `/outbound-missions` (`outbound_missions.router`), `/message-templates` (`message_templates.router`).
- Services: `outbound_delivery_service` / `OutboundDeliveryService` (the single send path — also consumed by voice's missed-call textback), `OutboundMissionService`, `handle_campaign_reply`, `CampaignConversationSyncer` and `check_guarantee_expiry` (both consumed by voice's inbound text + voice campaigns), `shorten_urls_in_text` (consumed by voice's Telnyx SMS), plus `message_renderer`, `sms_fallback`/`ai_fallback`, `campaign_lifecycle`, and campaign stats helpers.
- Frontend: `campaigns-list`, `campaign-detail`, `campaign-form`, `sms-campaign-wizard`, `voice-campaign-wizard`, plus `steps`/`sms-steps`/`voice-steps` wizard trees.

## How to Extract

1. Pull `core` plus `contacts`, `compliance`, `voice`, `offers`, `short-links`, `agent-brain`, and `hitl` transitively. Extract voice + messaging together (or behind a shared transport interface) to break the cycle.
2. Copy `owns_paths` (messaging/campaigns/outbound services, four routers, four workers, seven model files, frontend campaigns tree).
3. Sever sideways imports: inject the `TextMessageProvider` from voice; repoint `OutboundComplianceService`/`OptOutManager`/`GlobalOptOut` (compliance), `Offer` (offers), `ShortLink` (short-links), `apply_contact_filters`/`TagService` (contacts), `get_openai_bearer_token` (agent-brain), and `autonomy_mandate` (hitl).
4. Mount the four routers; wire `outbound_delivery_service` as the shared send path.
5. Set `CAMPAIGN_POLL_INTERVAL`, Telnyx, and mac-relay env vars.
6. Port the ten tables and their creating revisions; coordinate `phone_messages` ownership with the voice block (which also reads it).
7. Register the four workers plus the shared `base_campaign_worker` in the new runner.

## Risks

- **Voice↔messaging cycle:** delivery cannot send without voice's `TextMessageProvider`, and voice's telephony reuses messaging's reply/conversation/link helpers — split them together.
- **Compliance gating:** all sends pass through `OutboundComplianceService` + `OptOutManager`; dropping them risks unlawful/over-rate messaging and reputation damage.
- **Cross-block models:** renderers and missions read the `Offer` model directly (not via an API) and the link shortener writes `ShortLink` — both are hard model-level couplings to other blocks.
- **Shared worker base:** `base_campaign_worker` is shared with voice; vendor it carefully so behavior stays identical across both blocks.
- **In-process polling:** the campaign/drip workers poll on `CAMPAIGN_POLL_INTERVAL`; running multiple backend replicas multiplies every poll loop (see CLAUDE.md worker note).
