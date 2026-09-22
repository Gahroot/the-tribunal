---
id: widget
name: Embeddable Chat & Voice Widget
tier: A
status: extracted
summary: A drop-in, unauthenticated website widget that lets visitors chat, voice-call, or text an AI agent; pairs a vanilla-TS embed bundle with public backend embed endpoints.
owns_paths:
  - frontend/packages/widget/
  - backend/packages/widget/
public_api:
  - backend/packages/widget/src/tribunal_widget/__init__.py::get_router
  - backend/packages/widget/src/tribunal_widget/__init__.py::register_providers
  - backend/packages/widget/src/tribunal_widget/service.py::PublicEmbedService
  - backend/packages/widget/src/tribunal_widget/access.py::EmbedAccessService
  - backend/packages/widget/src/tribunal_widget/openai.py::EmbedOpenAIService
  - frontend/packages/widget/src/index.ts::AIAgentElement
  - frontend/packages/widget/src/render.ts
  - frontend/packages/widget/src/view.ts
  - frontend/packages/widget/src/styles.ts
depends_on: [core, voice, agent-brain, compliance]
external_integrations: [openai, telnyx]
env_vars:
  - DEMO_FROM_PHONE_NUMBER
  - DEMO_IP_RATE_LIMIT
  - DEMO_PHONE_RATE_LIMIT
  - DEMO_RATE_LIMIT_BYPASS_PHONES
  - OPENAI_REALTIME_IDLE_TIMEOUT_MS
  - API_BASE_URL
  - TELNYX_API_KEY
  - TELNYX_CONNECTION_ID
db_tables: []
alembic_migrations: none — owns no tables; reads shared agents/contacts/demo_requests created elsewhere in the shared chain
workers: []
extraction_effort: medium
extraction_notes: The most self-contained front-to-back capability (own frontend bundle + isolated public router), but its service layer reaches sideways into the voice block's Telnyx services, the agent-brain block's OpenAI Realtime/credentials helpers, and the compliance block's embed rate limiter; it also reads shared (unassigned) Agent/Contact/DemoRequest models.
---

## Overview

The widget is the public, embeddable surface of an AI agent. A site owner drops in the `frontend/src/widget/` bundle, which renders a chat/voice launcher and talks to the unauthenticated `/api/v1/p/embed/{public_id}/*` endpoints. Visitors can text-chat with the agent, open a live OpenAI Realtime voice session, or request an AI phone call / SMS back to their own number. Everything is keyed off an agent's `public_id` with origin allow-listing and IP/phone rate limits, so no auth or workspace token is exposed to the browser.

## Internal Dependencies

Sideways imports into other blocks that must be severed (from `docs/blocks/coupling-report.json`):

- `backend/app/services/embed/service.py:29: from app.services.telephony.telnyx import TelnyxSMSService` → **voice** — sends the embed "text me" greeting over SMS.
- `backend/app/services/embed/service.py:30: from app.services.telephony.telnyx_voice import TelnyxVoiceService` → **voice** — initiates the embed "call me" phone demo.
- `backend/app/services/embed/openai.py:14: from app.services.ai.image_input import build_chat_user_message_with_image` → **agent-brain** — builds multimodal chat messages.
- `backend/app/services/embed/openai.py:15: from app.services.ai.openai_credentials import OpenAICredentialError, resolve_openai_credentials` → **agent-brain** — resolves per-workspace OpenAI keys.
- `backend/app/services/embed/openai.py:16: from app.services.ai.openai_realtime_config import RealtimeSessionConfig, build_client_secret_request, build_realtime_session_config, extract_realtime_client_secret_value` → **agent-brain** — mints ephemeral Realtime tokens / session config.
- `backend/app/services/embed/access.py:13: from app.services.rate_limiting.embed_limiter import enforce_chat_rate_limits, enforce_token_rate_limits` → **compliance** — chat/token rate limiting.

Shared (currently *unassigned*, not owned by any block) imports also to carry along: `app.models.agent.Agent`, `app.models.contact.Contact`, `app.models.demo_request.DemoRequest`, and `app.schemas.embed.*`. Plus core: `app.api.deps.DB`, `app.core.config.settings`, `app.core.utils.get_client_ip`, `app.core.encryption.hash_phone`, `app.core.rate_limit_helpers.raise_rate_limited`, `app.services.idempotency.derive_outbound_key`.

## Public Surface

- Routes (mounted at `/api/v1/p/embed`): `GET /{public_id}/config`, `POST /{public_id}/token`, `POST /{public_id}/chat`, `POST /{public_id}/tool-call`, `POST /{public_id}/transcript`, `POST /{public_id}/call`, `POST /{public_id}/text`.
- Services: `PublicEmbedService.get_config / create_realtime_token / send_chat_message / execute_tool_call / save_transcript / trigger_call / trigger_text`; `EmbedAccessService` (origin + rate-limit enforcement); `EmbedOpenAIService` (chat + Realtime).
- Frontend: the `frontend/src/widget/` bundle (`widget.ts` entry/mount, `view.ts` view-model, `render.ts` DOM, `styles.ts` shadow-DOM CSS). Consumers embed the built bundle and pass an agent `public_id`.

## Status: extracted

This block is packaged into mountable workspace members. The block source no
longer lives in the app tree (`frontend/src/widget/`, `backend/app/services/embed/`,
`backend/app/api/v1/embed.py`); those paths were moved/severed:

- **Frontend** → `frontend/packages/widget/` (npm package `@tribunal/widget`).
- **Backend** → `backend/packages/widget/` (uv distribution `tribunal-widget`,
  importable as `tribunal_widget`).

The six sideways imports listed above are severed: the backend block imports core
only through `app.core_api` / `app.core` / `app.db` / `app.models` and borrows
Telnyx SMS/voice and OpenAI credential resolution through injection ports in
`tribunal_widget.providers` (the host registers concrete implementations in
`backend/app/blocks/widget_wiring.py`). The frontend package is self-contained
vanilla TS with zero imports from `frontend/src/components`, `src/lib`, or app
code (the embed `messaging`/`theme` helpers were vendored into the package).

### Install & mount (frontend)

1. The package is an npm workspace member; the app depends on it via
   `"@tribunal/widget": "*"` and `npm ci` from `frontend/` links it.
2. Build it: `npm run build -w @tribunal/widget` (tsup → `dist/` esm + d.ts).
3. Consume it: `import "@tribunal/widget"` registers the `<ai-agent>` custom
   element as a side effect, or import named exports
   (`AIAgentElement`, `WidgetView`, `buildWidgetMarkup`, `WIDGET_CSS`, …) from
   `@tribunal/widget`.
4. Tests live in the package and run with `npm run test -w @tribunal/widget`
   (standalone vitest/jsdom, no MSW/Next setup).

### Install & mount (backend)

1. The package is a uv workspace member (`backend/packages/widget/`); the host
   `backend/pyproject.toml` declares `tribunal-widget` as a workspace dependency.
   `uv sync` from `backend/` links it editable.
2. Mount the router (already wired in `app/api/v1/router.py`):
   ```python
   from tribunal_widget import get_router
   api_router.include_router(get_router())   # -> /api/v1/p/embed/...
   ```
   `get_router()` returns an `APIRouter` already prefixed `/p/embed` with the
   `Public Embed` tag.
3. Wire the injection ports once at startup (host adapter
   `app/blocks/widget_wiring.py`, imported for its side effect by the v1 router):
   ```python
   from tribunal_widget import register_providers
   register_providers(
       sms_sender_factory=...,        # Telnyx SMS (voice block)
       voice_caller_factory=...,      # Telnyx voice (voice block)
       credential_resolver=...,       # per-workspace OpenAI creds (agent-brain)
   )
   ```
   Provider gating, when an adapter is left unregistered: `GET /config` is the
   only fully provider-free route. `chat` and `token` (Realtime) both resolve
   OpenAI credentials, so without `credential_resolver` they return 503; `call`
   needs `voice_caller_factory` and `text` needs `sms_sender_factory`, each 503
   when unset.
4. Provide the declared `env_vars` (Telnyx + demo rate-limit + OpenAI Realtime
   idle timeout). The block owns no tables and no workers, so there are no
   migrations or `register_workers` to wire.

## How to Extract

> Historical guide (the extraction has been performed — see *Status: extracted*).

1. Pull `core` plus `voice`, `agent-brain`, and `compliance` (transitively).
2. Copy `frontend/src/widget/`, `backend/app/services/embed/`, and `backend/app/api/v1/embed.py`.
3. Sever the six sideways imports above: either vendor the Telnyx SMS/Voice clients, OpenAI Realtime helpers, and embed rate limiter into the new project, or replace them with the new project's equivalents behind the same call signatures.
4. Carry the shared `Agent`, `Contact`, `DemoRequest` models and `app/schemas/embed.py`.
5. Mount `embed.router` and set the `env_vars` above (Telnyx + demo rate-limit + OpenAI Realtime idle timeout).
6. No tables or workers to port.

## Risks

- **Voice/SMS coupling:** without the voice block's Telnyx services the "call me"/"text me" actions 503; chat/Realtime still work, so a chat-only extraction is viable by stubbing `trigger_call`/`trigger_text`.
- **Public attack surface:** these endpoints are unauthenticated. The origin allow-list (`agent.allowed_domains`) and the compliance rate limiter are the only abuse controls — do not drop them during extraction.
- **OpenAI credential resolution:** Realtime tokens depend on agent-brain's per-workspace credential lookup; mis-wiring leaks the wrong workspace's key or fails token minting.
