# OpenAI Realtime 2.0 + OAuth Voice Integration Plan

## Objective

Finish the OpenAI voice path in this CRM by upgrading the existing Realtime implementation to the current GA/2.0 session shape, wiring server-side token/session creation consistently for embed and test calls, and adding safe OpenAI OAuth credential refresh/resolution so workspace OpenAI credentials can be used without pasting short-lived tokens repeatedly.

## Current state

- `backend/app/core/config.py:35-41` already has `openai_api_key`, `openai_oauth_access_token`, `openai_oauth_refresh_token`, `openai_oauth_expires_at`, and `openai_oauth_account_id`, but no refresh client ID, refresh helper, or workspace-aware resolver.
- `backend/app/services/ai/openai_credentials.py:13-25` only returns `settings.openai_oauth_access_token or settings.openai_api_key`; it does not refresh expired OAuth tokens and does not read `WorkspaceIntegration` credentials.
- `backend/app/schemas/integration.py:31-39` and `frontend/src/components/settings/integration-config-dialog.tsx:100-143` already model OpenAI API key plus OAuth token fields, so no database migration is required for storing OpenAI OAuth credentials.
- `backend/app/services/ai/voice_agent.py:121-145`, `175-214`, and `694-703` use the older/beta Realtime shape: `modalities`, flat `voice`, flat `input_audio_format` / `output_audio_format`, `input_audio_noise_reduction`, and `temperature`.
- `backend/app/services/ai/voice_agent.py:427-470` and `frontend/src/app/embed/[publicId]/_use-voice-session.ts:518-580` primarily listen for old audio/transcript event names like `response.audio.delta` and `response.audio_transcript.delta`; GA emits `response.output_audio.delta` and `response.output_audio_transcript.delta`.
- `backend/app/api/v1/embed.py:247-353` mints public embed client secrets, but posts an old/incomplete body to `/v1/realtime/client_secrets`: `{"model":"gpt-4o-realtime-preview","voice":...}` instead of `{"session": {"type":"realtime", ...}}`.
- `frontend/src/app/embed/[publicId]/_use-voice-session.ts:385-439` and `frontend/src/app/voice-test/page.tsx:313-349` connect directly to `https://api.openai.com/v1/realtime/calls` with SDP and then send old-shape `session.update` payloads.
- `frontend/src/app/voice-test/page.tsx:273-275` calls `/api/v1/realtime/token/{agentId}?workspace_id=...`, but no matching FastAPI route exists in `backend/app/api/v1/router.py`.
- `backend/app/websockets/voice_bridge.py:146-165` only wires tool callbacks for Grok and ElevenLabs. OpenAI voice sessions do not currently implement `ToolCallableProtocol`, so OpenAI Realtime cannot execute `send_dtmf` / booking tools through the server-side telephony bridge.

## Verified Realtime 2.0 shape

- OpenAI Python SDK `openai>=2.36` is already required in `backend/pyproject.toml:69-72`.
- The installed/generated OpenAI SDK source at `openai-python/2.38.0` defines GA Realtime session config in `src/openai/types/realtime/realtime_session_create_request_param.py`:
  - required `type: "realtime"`
  - `model` allows `gpt-realtime`, `gpt-realtime-1.5`, `gpt-realtime-2`, `gpt-realtime-mini`, and dated snapshots
  - `output_modalities`, not old `modalities`
  - nested `audio.input` and `audio.output`, not flat audio fields
  - no `temperature` on the GA session
- `src/openai/types/realtime/realtime_audio_formats_param.py` defines `{"type":"audio/pcmu"}` for G.711 μ-law, replacing the old string `g711_ulaw`.
- `src/openai/types/realtime/realtime_audio_config_input_param.py` defines `audio.input.format`, `audio.input.noise_reduction`, `audio.input.transcription`, and `audio.input.turn_detection`.
- `src/openai/types/realtime/realtime_audio_config_output_param.py` defines `audio.output.format`, `audio.output.voice`, and optional `audio.output.speed`.
- `src/openai/types/realtime/client_secret_create_params.py` defines `/realtime/client_secrets` as accepting `session`, plus optional `expires_after`.
- `src/openai/lib/_realtime.py:58-93` confirms `/realtime/calls` can still take raw SDP when the session is already bound to a client secret, or multipart SDP plus session when not using a pre-bound secret.
- OpenAI’s public developer blog confirms the GA migration points: GA session shape, `gpt-realtime`, removal of arbitrary temperature from GA Realtime, `audio.input.turn_detection.idle_timeout_ms`, async function calling, and GA event names.

## Design

### Realtime configuration builder

Add a small backend builder module so all OpenAI Realtime session shapes are generated in one place instead of hand-coded in API routes, websockets, and frontend payloads.

Target file: `backend/app/services/ai/openai_realtime_config.py`

Core responsibilities:

- Normalize OpenAI voices to the supported set currently duplicated in `backend/app/api/v1/embed.py:274-287` and `frontend/src/lib/voice-constants.ts:9-20`.
- Map current telephony format `g711_ulaw` to GA Realtime `{"type":"audio/pcmu"}`.
- Build GA session payloads with:
  - `type: "realtime"`
  - configurable `model`, defaulting to `settings.openai_realtime_model`
  - `instructions`
  - `output_modalities: ["audio"]` for voice sessions
  - `audio.input.format`, `audio.input.transcription`, `audio.input.turn_detection`, `audio.input.noise_reduction`
  - `audio.output.format`, `audio.output.voice`
  - `tools` and `tool_choice` when tools are enabled
  - `truncation` retention-ratio config for long calls
  - `reasoning` only when using reasoning-capable models such as `gpt-realtime-2`
- Build `response.create` payloads with `output_modalities: ["audio"]` instead of old `modalities`.
- Preserve a compatibility helper for legacy providers that still expect flat fields, so Grok/ElevenLabs code does not get accidentally changed.

### Settings

Extend `backend/app/core/config.py:35-41` with non-secret tuning flags:

- `openai_realtime_model: str = "gpt-realtime-2"`
- `openai_realtime_client_secret_ttl_seconds: int = 600`
- `openai_realtime_idle_timeout_ms: int | None = 6000`
- `openai_oauth_client_id: str = ""`
- `openai_oauth_token_url: str = "https://auth.openai.com/oauth/token"`
- `openai_codex_voice_enabled: bool = False`

Keep API-key billing as the default production path. Treat ChatGPT/Codex OAuth voice as experimental unless a real Codex Realtime endpoint is verified with a live account.

### Credential resolver and OAuth refresh

Expand `backend/app/services/ai/openai_credentials.py` rather than scattering credential logic across routes.

Planned API:

- `OpenAICredentialContext`: frozen dataclass containing `bearer_token`, `source`, `account_id`, `organization_id`, `expires_at`, and `is_oauth`.
- `get_openai_bearer_token()` remains for existing synchronous callers and global env fallback.
- `is_openai_configured()` remains for compatibility.
- `async resolve_openai_credentials(db: AsyncSession | None = None, workspace_id: uuid.UUID | None = None, *, require_fresh: bool = True) -> OpenAICredentialContext`:
  - prefer active `WorkspaceIntegration` credentials for `integration_type == "openai"` when `workspace_id` and `db` are provided
  - support `api_key`, `access_token`, `refresh_token`, `expires_at`, `account_id`, `organization_id`
  - refresh OAuth tokens when expired or near expiry and `refresh_token` plus `settings.openai_oauth_client_id` are available
  - persist refreshed workspace credentials back to `WorkspaceIntegration.credentials`
  - fall back to env settings when workspace credentials are missing
- `refresh_openai_oauth_token(refresh_token: str) -> OpenAICredentialContext` ports the verified GG framework refresh logic from `packages/ggcoder/src/core/oauth/openai.ts:198-232`, but uses Python `httpx`, URL-safe JWT decoding, and config-driven client ID.

Security constraints:

- Never log bearer tokens, refresh tokens, raw JWTs, or client secrets.
- Return generic user-facing errors for token exchange failures; keep provider status codes in structured logs without bodies when they might contain secrets.
- Do not hard-code GG framework’s OpenAI OAuth client ID into this app; require `OPENAI_OAUTH_CLIENT_ID` if we need refresh. Existing pasted OAuth tokens can still be used until expiry.

### Authenticated Realtime token endpoint

Add `backend/app/api/v1/realtime.py` and include it in `backend/app/api/v1/router.py` with prefix `/realtime`.

Endpoint shape:

- `POST /api/v1/realtime/token/{agent_id}?workspace_id=...`
- Auth: existing `CurrentUser` plus `get_workspace` / `WorkspaceAccess` semantics.
- Input body: optional test overrides for `voice`, `instructions`, `turn_detection_threshold`, `silence_duration_ms`, and `initial_greeting`.
- Fetch `Agent` by `agent_id` and `workspace_id`.
- Resolve workspace OpenAI credentials with the new resolver.
- Build GA session config using `openai_realtime_config.py`.
- POST to `https://api.openai.com/v1/realtime/client_secrets` with:
  - `Authorization: Bearer <resolved token>`
  - `OpenAI-Organization` when present
  - `{"session": <GA session>, "expires_after": {"anchor":"created_at", "seconds": settings.openai_realtime_client_secret_ttl_seconds}}`
- Return the same basic `client_secret` shape expected by frontend plus `model`, safe agent metadata, and tool names. Do not return private system instructions unless the caller is authenticated and the UI truly needs them.

Compatibility:

- Keep `GET /api/v1/realtime/token/{agent_id}` temporarily as a thin wrapper or update `frontend/src/app/voice-test/page.tsx:273-275` to POST. Prefer POST because overrides belong in a body.

### Public embed token endpoint

Update `backend/app/api/v1/embed.py:247-353` to use the same builder and credential resolver.

Changes:

- Keep origin validation and rate limiting before OpenAI calls.
- Resolve credentials using `agent.workspace_id` so each workspace can use its own OpenAI integration when configured.
- Build and bind the full GA session server-side in the client secret request.
- Stop returning the private `agent.system_prompt` to public embed clients. The browser should not need it if the session is preconfigured by the server.
- Keep returning safe fields required by the widget: name, voice, language, initial greeting, model, and tool definitions needed for client-side tool-result routing.
- Update `backend/tests/api/test_embed_rate_limit.py:103-127` to assert the new `/client_secrets` body includes a `session` object and still enforces rate limits before the mocked OpenAI call.

### Backend OpenAI voice session upgrade

Update `backend/app/services/ai/voice_agent.py` to be a GA Realtime session.

Primary edits:

- `MODEL` at `backend/app/services/ai/voice_agent.py:39` should read from `settings.openai_realtime_model` at runtime or be passed into `__init__`.
- `connect()` at `backend/app/services/ai/voice_agent.py:56-104` should log only credential source/model, not key prefixes.
- `_configure_session()` at `backend/app/services/ai/voice_agent.py:109-149` should call the new GA config builder instead of constructing old flat fields.
- `configure_session()` at `backend/app/services/ai/voice_agent.py:150-214` should update nested `audio` fields and drop `temperature` for OpenAI GA Realtime.
- `send_greeting()` and `trigger_initial_response()` at `backend/app/services/ai/voice_agent.py:216-360` should send `response.create` with `output_modalities: ["audio"]` rather than old `modalities`.
- `receive_audio_stream()` at `backend/app/services/ai/voice_agent.py:380-655` should treat both legacy and GA event names as valid during migration:
  - `response.output_audio.delta` and `response.audio.delta`
  - `response.output_audio.done` and `response.audio.done`
  - `response.output_audio_transcript.delta` and `response.audio_transcript.delta`
  - `response.output_audio_transcript.done` and `response.audio_transcript.done`
  - `response.output_text.delta` and `response.text.delta`
  - `response.output_text.done` and `response.text.done`
- `inject_context()` at `backend/app/services/ai/voice_agent.py:656-713` should update only `instructions` plus invariant GA audio/session fields through the builder.
- `_send_event()` at `backend/app/services/ai/voice_agent.py:729-779` should log nested audio config keys and `output_modalities`, not flat fields.

### OpenAI server-side tools for phone calls

Bring OpenAI voice to parity with Grok/ElevenLabs tools.

Target files:

- `backend/app/services/ai/voice_agent.py`
- `backend/app/websockets/voice_bridge.py:146-165`
- `backend/app/services/ai/voice_session_factory.py:269-349`
- `backend/app/services/ai/protocols.py:158-193`

Implementation:

- Add `set_tool_callback()` and `submit_tool_result()` to `VoiceAgentSession` so it structurally satisfies `ToolCallableProtocol`.
- Add tool definitions to the OpenAI GA session via `get_tools_from_agent_config()` from `backend/app/services/ai/voice_tools.py:275-314`.
- Handle `response.function_call_arguments.done` in `receive_audio_stream()` by parsing arguments, calling the callback, submitting `function_call_output`, and triggering a follow-up `response.create`.
- Use task tracking for async tool calls so audio streaming does not deadlock while waiting on a slow external tool.
- Replace the concrete `isinstance(voice_session, (GrokVoiceAgentSession, ElevenLabsVoiceAgentSession))` check in `backend/app/websockets/voice_bridge.py:146-165` with the existing `supports_tools()` protocol helper so OpenAI receives the same server-side callback.
- Preserve DTMF behavior: OpenAI can call `send_dtmf`, and the callback created by `backend/app/services/ai/tool_executor.py:387-471` sends Telnyx DTMF via the current call control ID.

### Frontend Realtime 2.0 updates

Update both browser WebRTC callers.

Files:

- `frontend/src/app/embed/[publicId]/_types.ts:14-30`
- `frontend/src/app/embed/[publicId]/_use-voice-session.ts:330-451` and `514-580`
- `frontend/src/app/voice-test/page.tsx:273-349` and `362-370`

Changes:

- Add a small helper module, likely `frontend/src/lib/realtime-events.ts`, with predicates/constants for legacy and GA event names so embed and voice-test stay consistent.
- Use the new authenticated POST token endpoint from voice-test, passing edited prompt/voice/VAD overrides in the body.
- For public embed, rely on the server-bound session in the client secret; do not send a full old-shape `session.update` with instructions from the browser.
- If a client-side update is still needed for dynamic test controls, send GA `session.update`:
  - `session.type = "realtime"`
  - `session.output_modalities = ["audio"]`
  - `session.audio.input.transcription = { model: "gpt-4o-mini-transcribe" }` or a configured transcription model
  - `session.audio.input.turn_detection = { type: "server_vad", threshold, prefix_padding_ms, silence_duration_ms }`
  - `session.audio.output.voice = voice`
- Listen for both GA and legacy event names to avoid breaking any non-OpenAI-compatible providers during rollout.
- Update `frontend/src/types/voice.ts:14-15` to include the GA format names or keep it explicitly legacy if only used for old UI state.

### Experimental Codex/OAuth voice boundary

Do not make ChatGPT/Codex OAuth the default voice path.

Rationale:

- The GG framework’s `gg-voice` Codex Realtime adapter only points at `https://chatgpt.com/backend-api/codex` and marks the route experimental.
- The stable, documented Realtime voice path is `api.openai.com/v1/realtime` with API billing and client secrets.
- ChatGPT subscription entitlement for Codex is not the same as OpenAI API billing, and the Codex Realtime request shape is internal.

Safe integration point:

- Implement OAuth token storage/refresh and account ID handling now.
- Add `openai_codex_voice_enabled` as a disabled feature flag.
- If later enabled, add a separate provider value such as `openai-codex-experimental` rather than changing `openai` semantics.
- Require a live, non-production proof before exposing Codex voice in UI: successful auth refresh, successful session/call creation, and a captured Realtime event stream without relying on undocumented assumptions.

## Risks

- GA Realtime removes `temperature`; existing agent `temperature` remains valid for text/chat paths but should not be sent to OpenAI Realtime GA.
- `gpt-realtime-2` may have different pricing/entitlements than `gpt-realtime`; keep the model env-configurable.
- Public embed currently exposes `agent.system_prompt`; removing it is a security improvement but may require frontend assumptions to change.
- Workspace credential resolution changes behavior for workspaces that have stale OpenAI integration credentials; tests must verify fallback and error messages.
- Async tool calls inside the Realtime receive loop can create runaway tasks if not tracked and cancelled on disconnect.
- Codex/ChatGPT OAuth voice remains experimental until a real endpoint is verified; do not promise subscription-backed voice without that proof.

## Verification

- Backend static checks after backend edits: `cd backend && uv run ruff check app && uv run mypy app`.
- Frontend checks after frontend edits: `cd frontend && npm run lint && npm run build`.
- Targeted backend tests:
  - `cd backend && uv run pytest backend/tests/api/test_embed_rate_limit.py`
  - new tests for the Realtime session builder and credential resolver
  - existing voice websocket tests under `backend/tests/voice_ws/`
- Runtime probe after backend route changes when a dev server and seeded agent are available: use `.gg/eyes/http.sh` against the new token endpoint and inspect that the response shape is stable and no secret values are logged.
- Visual probe after editing `frontend/src/app/voice-test/page.tsx` or embed UI: run `.gg/eyes/visual-web.sh http://localhost:3000/voice-test` and inspect the screenshot for regressions.
- Manual/live verification requiring user-provided credentials: place a non-production OpenAI API key or OAuth credentials in a test workspace integration, open `/voice-test`, complete a short WebRTC call, confirm user transcript, assistant audio, and no `error` events in backend logs.

## Steps

1. Add `backend/app/services/ai/openai_realtime_config.py` with GA Realtime session, response, audio-format, voice-normalization, and tool-config builders based on OpenAI SDK 2.38 generated types.
2. Extend `backend/app/core/config.py` with Realtime model, client-secret TTL, idle-timeout, OAuth client ID/token URL, and disabled Codex voice feature-flag settings.
3. Expand `backend/app/services/ai/openai_credentials.py` with `OpenAICredentialContext`, workspace integration lookup, OAuth refresh, account ID extraction, organization header support, env fallback, and no-secret logging behavior.
4. Add backend tests for credential resolution and refresh behavior, including workspace integration precedence, expired OAuth refresh persistence, env fallback, and missing-credential errors.
5. Update `backend/app/api/v1/embed.py` to create GA `/v1/realtime/client_secrets` requests through the new builder/resolver and stop returning public system prompts.
6. Add `backend/app/api/v1/realtime.py` with an authenticated workspace/agent token endpoint for `/voice-test`, include it in `backend/app/api/v1/router.py`, and cover it with API tests.
7. Update `backend/app/services/ai/voice_agent.py` to use GA session/update/response payloads, nested audio config, new event names with legacy compatibility, and safe logging.
8. Add OpenAI tool-calling support to `VoiceAgentSession`, then update `backend/app/websockets/voice_bridge.py` and `backend/app/services/ai/voice_session_factory.py` to use `supports_tools()` so OpenAI phone calls can execute DTMF and booking tools.
9. Update `frontend/src/app/embed/[publicId]/_types.ts` and `frontend/src/app/embed/[publicId]/_use-voice-session.ts` to rely on server-bound GA sessions, remove public prompt handling, and support GA plus legacy Realtime event names.
10. Update `frontend/src/app/voice-test/page.tsx` to call the new authenticated token endpoint with test overrides, send GA `session.update` only when needed, and support GA plus legacy Realtime event names.
11. Regenerate `backend/openapi.json` and `frontend/src/lib/api/_generated.ts` if the project’s API contract workflow requires generated client types for the new endpoint.
12. Run targeted backend tests, then `cd backend && uv run ruff check app && uv run mypy app`, and fix all failures.
13. Run `cd frontend && npm run lint && npm run build`, and fix all failures.
14. If local dev servers and credentials are available, verify the token endpoint with `.gg/eyes/http.sh`, verify `/voice-test` visually with `.gg/eyes/visual-web.sh`, and perform one short non-production Realtime voice call while checking backend logs for Realtime errors.
