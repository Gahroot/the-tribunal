---
id: agent-brain
name: Agent Brain (AI, Prompts & A/B Bandit)
tier: C
status: manifest
summary: The AI cognition layer — agent definitions/templates, prompt building, the real-time voice/text agent sessions (OpenAI Realtime / ElevenLabs / Grok), the CRM-assistant tool stack, IVR navigation, qualification, and the prompt-versioning + multi-armed-bandit A/B experimentation engine that learns which prompts and messages convert.
owns_paths:
  - backend/app/services/agents/
  - backend/app/services/ai/
  - backend/app/services/message_tests/
  - backend/app/api/v1/agents.py
  - backend/app/api/v1/prompt_versions.py
  - backend/app/api/v1/message_tests.py
  - backend/app/models/agent.py
  - backend/app/models/prompt_version.py
  - backend/app/models/prompt_version_stats.py
  - backend/app/models/bandit_decision.py
  - backend/app/models/message_test.py
  - backend/app/workers/prompt_improvement_worker.py
  - backend/app/workers/prompt_stats_worker.py
  - backend/app/workers/message_test_worker.py
  - backend/app/workers/experiment_evaluation_worker.py
  - frontend/src/components/agents/
  - frontend/src/components/experiments/
public_api:
  - backend/app/api/v1/agents.py::router
  - backend/app/api/v1/prompt_versions.py::router
  - backend/app/api/v1/message_tests.py::router
  - backend/app/services/agents/agent_service.py::AgentService
  - backend/app/services/ai/embeddings.py::embed_texts
  - backend/app/services/ai/embeddings.py::Embedder
  - backend/app/services/ai/openai_credentials.py::get_openai_bearer_token
  - backend/app/services/ai/openai_credentials.py::is_openai_configured
  - backend/app/services/ai/voice_session_factory.py::create_workspace_voice_session
  - backend/app/services/ai/qualification.py::analyze_and_qualify_contact
  - backend/app/services/ai/qualification.py::batch_analyze_contacts
  - backend/app/services/ai/text_agent.py::schedule_ai_response
  - backend/app/services/ai/crm_assistant/_processor.py::process_assistant_message
  - backend/app/services/ai/opt_out_detector.py::has_potential_opt_out_keywords
  - backend/app/services/ai/prompt_version_service.py::PromptVersionService
  - backend/app/services/message_tests/message_test_service.py::MessageTestService
  - frontend/src/components/agents/agents-list.tsx
  - frontend/src/components/agents/create-agent-form.tsx
  - frontend/src/components/agents/ab-test-dashboard.tsx
  - frontend/src/components/experiments/experiments-list.tsx
  - frontend/src/components/experiments/message-test-wizard.tsx
depends_on: [core, appointments, automations, hitl, knowledge, messaging, offers, payments, voice]
external_integrations: [openai, elevenlabs]
env_vars:
  - OPENAI_API_KEY
  - OPENAI_REALTIME_MODEL
  - OPENAI_REALTIME_CLIENT_SECRET_TTL_SECONDS
  - OPENAI_REALTIME_IDLE_TIMEOUT_MS
  - OPENAI_OAUTH_CLIENT_ID
  - OPENAI_OAUTH_REFRESH_TOKEN
  - OPENAI_OAUTH_ACCESS_TOKEN
  - XAI_API_KEY
  - ELEVENLABS_API_KEY
db_tables:
  - backend/app/models/agent.py::agents
  - backend/app/models/prompt_version.py::prompt_versions
  - backend/app/models/prompt_version_stats.py::prompt_version_stats
  - backend/app/models/bandit_decision.py::bandit_decisions
  - backend/app/models/message_test.py::message_tests
  - backend/app/models/message_test.py::test_variants
  - backend/app/models/message_test.py::test_contacts
alembic_migrations: shared linear chain — agents (e6c0ca7dd25e_initial_schema), prompt_versions + prompt_version_stats (u5v6w7x8y9z0_add_prompt_instrumentation), bandit_decisions (v6w7x8y9z0a1_add_bandit_infrastructure), message_tests + test_variants + test_contacts (m7n8o9p0q1r2_add_message_tests).
workers:
  - backend/app/workers/prompt_improvement_worker.py
  - backend/app/workers/prompt_stats_worker.py
  - backend/app/workers/message_test_worker.py
  - backend/app/workers/experiment_evaluation_worker.py
extraction_effort: high
extraction_notes: Agent-brain is the AI hub and the most fanned-out block in the graph — it imports appointments (BookingService, staff assignment), messaging (campaign lifecycle, outbound delivery, message_trace), voice (text_provider, telnyx_voice, call_transfer, audio codec), payments (call_payment_service, CallPayment), hitl (approval_gate_service, autonomy BATCH_PACKS), knowledge (knowledge_context_service, search_tool), offers (Offer model + prestyj sequences), and emits to automations. Conversely voice/contacts/hitl/knowledge import back into it, so it sits at the center of several cycles. There is no `experiments.py` router — A/B experiments are surfaced through `message_tests.py` plus the frontend `experiments/` tree.
---

## Overview

Agent Brain is the cognition layer of The Tribunal: it decides what the AI agent says and learns what works. It owns agent definitions and templates (`services/agents/`), the entire AI runtime (`services/ai/`) — prompt building, the real-time voice agent sessions over OpenAI Realtime / ElevenLabs / Grok, IVR navigation, the CRM-assistant tool executor stack, transcript analysis, qualification, embeddings, and opt-out detection — and the A/B testing engine (`services/message_tests/`). Its **differentiator is the prompt-versioning + multi-armed-bandit experimentation loop**: every prompt is a versioned artifact (`prompt_versions`), bandit arm selection picks variants to try (`bandit_decisions`), rewards are attributed back from real conversation outcomes (`prompt_version_stats`, `reward_config`), and `message_tests` run controlled A/B variant trials across contacts. The `prompt_improvement_worker`, `prompt_stats_worker`, `message_test_worker`, and `experiment_evaluation_worker` close that learning loop in the background. This turns prompts from static strings into an optimization surface — the thing that makes the agent measurably better over time rather than just configured.

## Internal Dependencies

Sideways block imports to sever (non-`core`, from `docs/blocks/coupling-report.json`):

- `backend/app/services/ai/base_tool_executor.py:18,87: from app.services.calendar.booking import BookingService` / `staff_assignment import resolve_staff_for_booking, staff_to_assignment_dict` → **appointments** — the agent books and assigns staff as a tool action.
- `backend/app/services/ai/call_context.py:181 & crm_assistant/_offer_tools.py:9: from app.models.offer import Offer`; `agents/templates.py:6 & ...` pull `app.services.offers.prestyj_batch_video_ads` sequences/pack terms → **offers** — offer context for prompts and tools.
- `backend/app/services/ai/crm_assistant/_campaign_tools.py:17 & _outbound_tools.py:6 & text_agent.py:35 & text_response_generator.py:38: from app.services.campaigns... / outbound...` → **messaging** — campaign lifecycle control, outbound growth workflow, and `message_trace` drafting from assistant/text tools.
- `backend/app/services/ai/crm_assistant/_campaign_tools.py:81 & _processor.py:748 & text_agent.py:211 & tool_executor.py:*: from app.services.telephony.text_provider import get_text_message_provider` / `telnyx_voice import TelnyxVoiceService` / `call_transfer import ...`; `ivr/transcriber.py:9: from app.services.audio.codec import mulaw_to_pcm` → **voice** — sending SMS, placing/transferring calls, and audio decode from AI tools and IVR.
- `backend/app/services/ai/crm_assistant/_payment_tools.py:127,38 & tool_executor.py:457,498,500,735: from app.services.payments import call_payment_service` / `from app.models.call_payment import CallPayment, CallPaymentStatus` → **payments** — in-call deposit/payment tooling.
- `backend/app/services/ai/crm_assistant/_payment_tools.py:31: from app.services.autonomy_mandate import BATCH_PACKS`; `_tool_executor.py:22 & text_tool_executor.py:42 & tool_executor.py:24 & outbound_improvement_suggestion_service.py:25: from app.services.approval.approval_gate_service import approval_gate_service/ApprovalGateService` → **hitl** — gating high-risk actions behind human approval and the autonomy mandate.
- `backend/app/services/ai/roleplay/agent_responder.py:25 & text_response_generator.py:37 & text_tool_executor.py:221 & tool_executor.py:846: from app.services.knowledge.knowledge_context_service / search_tool import ...` → **knowledge** — RAG context and knowledge search as a tool.
- `backend/app/services/ai/roleplay/roleplay_service.py:35: from app.services.automations.events import EVENT_ROLEPLAY_COMPLETED, emit_automation_event` → **automations** — sanctioned automation-bus hook (keep, don't sever).

Core: `app.api.deps`, `app.db.scope`, `app.db.pagination`, `app.db.session.AsyncSessionLocal`, `app.core.config.settings`, `app.core.encryption`, `app.core.circuit_breakers`, `app.core.metrics`, `app.services.idempotency.derive_outbound_key`.

## Public Surface

- Authenticated REST routes: `/api/v1/workspaces/{workspace_id}/agents` (`agents.router`), `/prompt-versions` (`prompt_versions.router`), `/message-tests` (`message_tests.router`). No standalone `experiments` router exists — experiments are message-test driven.
- Services consumed by other blocks: `embed_texts`/`Embedder` (knowledge embeddings), `get_openai_bearer_token`/`is_openai_configured` (messaging AI fallback, voice credentials), `create_workspace_voice_session` and the voice/Grok/ElevenLabs session classes (voice bridge), `schedule_ai_response` + `process_assistant_message` (voice inbound text + operator CRM assistant), `analyze_and_qualify_contact`/`batch_analyze_contacts` (contacts), `has_potential_opt_out_keywords` (voice missed-call textback), `PromptVersionService`, `MessageTestService`, `AgentService`.
- Frontend: `agents/` (agents list, create-agent form, AB-test dashboard, practice arena, embed dialog) and `experiments/` (experiments list, message-test wizard, variant editor, test analytics, template dialogs).

## How to Extract

1. Pull `core` plus the full closure: `appointments`, `automations`, `hitl`, `knowledge`, `messaging`, `offers`, `payments`, `voice`. Agent-brain sits at the center of several cycles (voice↔agent-brain, contacts↔agent-brain, hitl↔agent-brain, knowledge↔agent-brain), so plan to extract the cognition core together with voice or behind injected protocols.
2. Copy `owns_paths` (agents/ai/message_tests services, three routers, five model files, four workers, agents + experiments frontend trees).
3. Sever sideways imports by injecting interfaces: a booking/staff port (appointments), a transport port for `text_provider`/`telnyx_voice`/`call_transfer` (voice), a payments port (`call_payment_service`), an approval/autonomy port (hitl), a knowledge-context/search port (knowledge), the `Offer` model + prestyj sequences (offers), and campaign/outbound/message-trace ports (messaging). Keep the roleplay `emit_automation_event` hook if the automation bus comes along.
4. Mount the three routers; export the embeddings, OpenAI-credential, voice-session-factory, qualification, and text-agent symbols that other blocks call.
5. Set the OpenAI env vars (`OPENAI_API_KEY`, realtime model/TTL/idle, OAuth client/refresh/access) plus `XAI_API_KEY` and `ELEVENLABS_API_KEY` (the latter two shared with voice).
6. Port the seven tables and their creating revisions; `bandit_decisions`/`prompt_versions`/`prompt_version_stats`/`message_tests` carry the experimentation state — port them together so the learning loop stays intact.
7. Register the four workers in the new runner gated on `RUN_BACKGROUND_WORKERS`.

## Risks

- **Center-of-graph entanglement:** agent-brain both imports and is imported by voice, contacts, hitl, and knowledge — extracting it alone leaves dangling imports in either direction; define the seams before cutting.
- **Credential/session coupling:** the voice block's bridge is *supplied* by agent-brain's `voice_session_factory` and `openai_credentials`; breaking these without a session-factory protocol breaks live voice.
- **Experimentation integrity:** bandit arm selection, reward attribution, and prompt stats span four tables and four workers; porting a subset silently degrades the A/B engine to no-ops or biased rewards.
- **Tool-action blast radius:** the CRM-assistant tool executor reaches into payments, messaging, voice, and appointments to take real actions; dropping the `approval_gate_service`/autonomy mandate gating risks unattended high-risk actions.
- **Embeddings dimension lock:** `embeddings.py::EMBEDDING_DIM` is referenced by knowledge's `knowledge_chunk` model column; changing the model/dim during extraction invalidates stored pgvector embeddings.
