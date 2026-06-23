---
id: voice
name: Voice & Telephony (Crown Jewel)
tier: B
status: manifest
summary: The crown-jewel real-time AI voice/telephony stack — Telnyx voice + SMS, the OpenAI Realtime / ElevenLabs / Grok voice bridge, live-call supervision, inbound routing/screening, voicemail, missed-call textback, voice campaigns, roleplay, and call outcome/feedback capture.
owns_paths:
  - backend/app/services/calls/
  - backend/app/services/telephony/
  - backend/app/services/audio/
  - backend/app/websockets/
  - backend/app/api/v1/calls.py
  - backend/app/api/v1/voice_campaigns.py
  - backend/app/api/v1/roleplay.py
  - backend/app/api/v1/call_feedback.py
  - backend/app/api/v1/call_outcomes.py
  - backend/app/workers/voice_campaign_worker.py
  - backend/app/workers/transcript_analysis_worker.py
  - backend/app/models/call_feedback.py
  - backend/app/models/call_outcome.py
  - backend/app/models/caller_memory.py
  - backend/app/models/phone_number.py
  - backend/app/models/phone_number_stats.py
  - frontend/src/components/calls/
  - frontend/src/app/calls/
public_api:
  - backend/app/api/v1/calls.py::router
  - backend/app/api/v1/voice_campaigns.py::router
  - backend/app/api/v1/roleplay.py::router
  - backend/app/api/v1/call_feedback.py::router
  - backend/app/api/v1/call_outcomes.py::router
  - backend/app/websockets/voice_bridge.py::router
  - backend/app/websockets/call_supervisor.py::router
  - backend/app/websockets/voice_test.py::router
  - backend/app/services/telephony/telnyx.py::TelnyxSMSService
  - backend/app/services/telephony/telnyx_voice.py::TelnyxVoiceService
  - backend/app/services/telephony/text_provider.py::get_text_message_provider
  - backend/app/services/telephony/text_provider.py::TextMessageProvider
  - backend/app/services/calls/live_call_registry.py::get_live_call_registry
  - frontend/src/components/calls/calls-list.tsx
  - frontend/src/components/calls/live-calls-panel.tsx
  - frontend/src/components/calls/live-call-supervisor.tsx
  - frontend/src/components/calls/transcript-viewer.tsx
  - frontend/src/components/calls/call-outcome-controls.tsx
depends_on: [core, agent-brain, compliance, contacts, messaging, automations, hitl]
external_integrations: [openai, elevenlabs, telnyx, mac-relay]
env_vars:
  - TELNYX_API_KEY
  - TELNYX_CONNECTION_ID
  - ELEVENLABS_API_KEY
  - XAI_API_KEY
  - TEXT_MESSAGE_PROVIDER
  - MAC_RELAY_BASE_URL
  - MAC_RELAY_TOKEN
  - MAC_RELAY_DEFAULT_SERVICE
  - AI_RESPONSE_DELAY_MS
  - VOICE_BRIDGE_MAX_CONNECTIONS
  - VOICE_WORKSPACE_MAX_SESSIONS
  - VOICE_TEST_MAX_CONNECTIONS
  - VOICE_MAX_CALL_DURATION_SECONDS
  - VOICE_HEARTBEAT_INTERVAL_SECONDS
  - VOICE_PONG_TIMEOUT_SECONDS
  - VOICE_LIVE_SENTIMENT_ENABLED
  - VOICE_SENTIMENT_ESCALATION_THRESHOLD
  - VOICE_SENTIMENT_SMOOTHING
  - VOICE_SENTIMENT_SUSTAINED_TURNS
db_tables:
  - backend/app/models/call_feedback.py::call_feedback
  - backend/app/models/call_outcome.py::call_outcomes
  - backend/app/models/caller_memory.py::caller_memories
  - backend/app/models/phone_number.py::phone_numbers
  - backend/app/models/phone_number_stats.py::phone_number_daily_stats
alembic_migrations: shared linear chain — caller_memories (20260610_caller_memory), call_outcomes + call_feedback (u5v6w7x8y9z0_add_prompt_instrumentation), phone_number_daily_stats (f1a2b3c4d5e6_add_sms_compliance_rate_limiting), phone_numbers (e6c0ca7dd25e_initial_schema, sender fields 20260520_mac_relay_sender_fields)
workers:
  - backend/app/workers/voice_campaign_worker.py
  - backend/app/workers/transcript_analysis_worker.py
extraction_effort: high
extraction_notes: Crown-jewel and the most entangled block — the voice bridge imports ~20 symbols from agent-brain (voice/Grok/ElevenLabs sessions, IVR gate, tool executor, OpenAI credentials, live sentiment, call context, caller memory) and telephony pulls messaging (link shortener, conversation syncer, reply handler, outbound delivery), contacts (engagement scoring), compliance (OptOutManager), hitl (command processor), and automations (missed-call events); voice and messaging form a real import cycle via TelnyxSMSService/text_provider.
---

## Overview

Voice is The Tribunal's headline capability: AI agents that answer and place phone calls in real time. It owns the entire telephony substrate — Telnyx voice + SMS (`telnyx.py`, `telnyx_voice.py`), the WebSocket media bridge that streams audio between Telnyx and an OpenAI Realtime / ElevenLabs / Grok voice session (`websockets/voice_bridge.py`), audio codec/buffering (`services/audio/`), inbound routing/screening/text handling, voicemail, missed-call textback, live-call supervision, and the in-browser voice test harness. On top of that sit voice campaigns (outbound dialing), agent roleplay, and post-call outcome/feedback capture and transcript analysis. It is the crown jewel: the highest-value, highest-complexity, most-integration-bound block in the repo.

## Internal Dependencies

Sideways block imports to sever (non-`core`, from `docs/blocks/coupling-report.json`):

- `backend/app/websockets/voice_bridge.py:31-39,288-289,738: from app.services.ai... import ...` → **agent-brain** — the live voice session itself: `VoiceAgentSession`, `ElevenLabsVoiceAgentSession`, `GrokVoiceAgentSession`, `voice_session_factory.create_workspace_voice_session`, `ivr.gate.IVRGate`, `tool_executor.create_tool_callback`, `openai_credentials.is_openai_configured`, `protocols.supports_tools`, `call_context.lookup_call_context/save_call_transcript`, `live_sentiment.LiveSentimentScorer`, `caller_memory_service.summarize_and_store_call`.
- `backend/app/websockets/voice_test.py:24-27: from app.services.ai... import ...` → **agent-brain** — test-harness mirror of the voice/Grok/ElevenLabs sessions and OpenAI credential resolution.
- `backend/app/api/v1/roleplay.py:24: from app.services.ai.roleplay import RoleplayService` → **agent-brain** — agent roleplay/training sessions.
- `backend/app/services/audio/codec.py:30: from app.services.ai.exceptions import AudioConversionError` → **agent-brain** — shared AI exception type.
- `backend/app/services/telephony/voicemail.py:49,154,178: from app.services.ai.call_context / openai_credentials import ...` → **agent-brain** — transcript persistence + OpenAI client for voicemail handling.
- `backend/app/services/telephony/missed_call_textback.py:49: from app.services.ai.opt_out_detector import has_potential_opt_out_keywords` → **agent-brain** — opt-out keyword detection.
- `backend/app/services/telephony/inbound_text.py:21,144: from app.services.ai.text_agent import schedule_ai_response` / `crm_assistant import process_assistant_message` → **agent-brain** — inbound SMS AI replies + operator CRM assistant.
- `backend/app/services/telephony/inbound_text.py:22: from app.services.approval.command_processor_service import command_processor_service` → **hitl** — operator command processing over SMS.
- `backend/app/services/telephony/inbound_text.py:23,510: from app.services.campaigns.conversation_syncer / reply_handler import ...` → **messaging** — sync inbound texts into campaign conversations and route campaign replies.
- `backend/app/services/telephony/inbound_text.py:270 & telnyx.py:405: from app.services.contacts.engagement_score import record_engagement` → **contacts** — engagement scoring on inbound/outbound activity.
- `backend/app/services/telephony/telnyx.py:28: from app.services.messaging.link_shortener import shorten_urls_in_text` → **messaging** — shortens links in outbound SMS.
- `backend/app/services/telephony/missed_call_textback.py:50: from app.services.automations.events import EVENT_MISSED_CALL, emit_automation_event` → **automations** — sanctioned automation-bus hook (keep, don't sever).
- `backend/app/services/telephony/missed_call_textback.py:51: from app.services.outbound.delivery import OutboundDeliveryChannel, OutboundDeliveryRequest, OutboundDeliveryStatus, outbound_delivery_service` → **messaging** — delivers the textback through the outbound pipeline.
- `backend/app/services/telephony/inbound_screening.py:51 & missed_call_textback.py:57: from app.services.rate_limiting.opt_out_manager import OptOutManager` → **compliance** — opt-out enforcement before any SMS send.
- `backend/app/workers/voice_campaign_worker.py: BaseCampaignWorker` (`app/workers/base_campaign_worker.py`) — **shared worker base** also used by messaging's `campaign_worker`; a shared dependency, not owned by voice.

Core: `app.api.deps`, `app.db.scope`, `app.db.pagination`, `app.core.config.settings`, `app.core.encryption`, `app.services.idempotency`, `app.workers.base`/`retryable`, `app.db.session.AsyncSessionLocal`.

## Public Surface

- Authenticated REST routes: `/api/v1/workspaces/{workspace_id}/calls` (`calls.router`), `/voice-campaigns` (`voice_campaigns.router`), `/roleplay` (`roleplay.router`), `/calls/{message_id}/outcome` (`call_outcomes.router`), `/calls/{message_id}/feedback` (`call_feedback.router`).
- WebSocket routes (mounted in `main.py`): `WS /voice/stream/{call_id}` (Telnyx media bridge), `WS /voice/test/{workspace_id}/{agent_id}` (browser test harness), `WS /voice/supervise/{workspace_id}/{call_id}` (live supervision) — all authenticated via short-lived `/auth/ws-ticket` JWT.
- Services: `TelnyxSMSService` (outbound SMS — heavily reused across the repo), `TelnyxVoiceService`, `get_text_message_provider`/`TextMessageProvider` (Telnyx vs mac-relay/iMessage selection), `get_live_call_registry`/`LiveCallRegistry` (in-process live-call state), plus inbound routing/screening/voicemail/missed-call-textback services and `phone_number_resolver`/`voice_agent_resolver`.
- Frontend: `calls-list`, `live-calls-panel`, `live-call-supervisor`, `transcript-viewer`, `call-outcome-controls`; `app/calls/` route.

## How to Extract

1. Pull `core` plus `agent-brain`, `compliance`, `contacts`, `messaging`, `automations`, and `hitl` transitively. Because `messaging` itself depends on `voice` (`text_provider`/`TelnyxSMSService`), plan to extract voice + messaging together or define a shared telephony interface to break the cycle.
2. Copy `owns_paths` (calls/telephony/audio services, websockets, five routers, two workers, five models, frontend tree + route).
3. Sever the agent-brain imports first — they are the bulk of the bridge. The cleanest seam is to define a `VoiceSessionFactory` protocol in voice and inject the concrete OpenAI/ElevenLabs/Grok session from agent-brain, rather than importing it directly.
4. Repoint messaging/contacts/compliance/hitl imports (link shortener, conversation syncer, reply handler, outbound delivery, engagement scoring, OptOutManager, command processor). Keep the `emit_automation_event` missed-call hook if the new project retains the automation bus.
5. Set the integration env vars (Telnyx, ElevenLabs, Grok/`XAI_API_KEY`, mac-relay) plus the `VOICE_*` tuning knobs. OpenAI Realtime credentials resolve through agent-brain's `openai_credentials`, not directly here.
6. Port the five tables and their creating revisions; share `phone_messages` ownership with messaging (that table is owned by the messaging block).
7. Register `voice_campaign_worker` and `transcript_analysis_worker` (and the shared `base_campaign_worker`) in the new runner; wire the three WebSocket routers and five REST routers.

**Recommended extraction level: Level 3 (standalone service).** Voice carries hard real-time constraints (WebSocket media streaming, per-call connection limits, in-process `LiveCallRegistry` state, voice-bridge concurrency caps). It should be pulled out as its own deployable service with a dedicated process and scaling profile rather than decoupled-in-place, communicating with the rest of the platform over an API/event boundary.

## Risks

- **Real-time/stateful coupling:** `LiveCallRegistry` and the voice bridge hold per-call in-process state and enforce connection limits; running multiple replicas without sticky routing or shared coordination breaks live supervision and concurrency caps.
- **Agent-brain entanglement:** the voice session is supplied entirely by agent-brain; without a clean session-factory seam, voice cannot run.
- **Voice↔messaging cycle:** `TelnyxSMSService`/`text_provider` are owned by voice but consumed by messaging's outbound delivery, while telephony consumes messaging's reply/conversation/link-shortener helpers — neither extracts cleanly alone.
- **Telephony/compliance safety:** inbound screening, missed-call textback, and SMS sends gate on `OptOutManager`; dropping it risks contacting opted-out numbers (regulatory + deliverability hazard).
- **Migration sharing:** `phone_numbers` originates in the initial schema and gains columns across later revisions; `phone_messages` is owned by messaging — coordinate table ownership during a split.
