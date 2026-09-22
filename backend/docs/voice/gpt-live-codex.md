# GPT-Live on the Codex subscription (`voice_provider = "live"`)

Runs `gpt-live-1-codex` through the local Codex CLI's `app-server` realtime
route, billed against a ChatGPT/Codex subscription instead of OpenAI API usage.

**Status: opt-in and off by default.** Read the limits before enabling it for
anything customer-facing.

## Why this is not the default

| | Realtime API (`openai`) | GPT-Live via Codex (`live`) |
|---|---|---|
| Auth | Per-workspace API key / OAuth | One host-wide `codex login` |
| Billing | Metered, billable to customers | ChatGPT plan allowance |
| Capacity | Scales with spend | Rolling ~5h window, shared by all calls |
| Multi-tenant | Yes | No — one ChatGPT account per host |
| Terms | Standard API terms | Consumer plan; automated resale is a real risk |

The capacity limit is the operational trap: the remaining allowance is **not
exposed to clients**, so the backend cannot check budget before dialling. It
meters locally from `session.usage.updated` and logs `live_voice_usage`, but a
campaign can still exhaust the window mid-call. Do not point outbound campaigns
at this provider.

`gpt-live-1` is also available on the public API (`v1/live/sessions`, $0.05/min).
That is a different transport from this one and is not implemented here.

## Setup

```bash
npm i -g @openai/codex   # needs >= 0.154 for realtime_conversation
codex login              # ChatGPT account, not an API key
```

```bash
LIVE_VOICE_ENABLED=true
LIVE_VOICE_CODEX_BINARY=/usr/local/bin/codex   # optional; PATH is searched
LIVE_VOICE_THREAD_MODEL=                       # must be ChatGPT-valid if set
LIVE_VOICE_ICE_SERVERS=stun:stun.l.google.com:19302
```

Then set an agent's `voice_provider` to `live`.

`OPENAI_API_KEY`, `CODEX_API_KEY` and `OPENAI_BASE_URL` are stripped from the
app-server's environment on purpose — leaving them set silently moves the
session onto metered API billing.

## Transport

```
Telnyx ──μ-law──▶ MuLawRelayTrack ──WebRTC/PCMU──▶ ChatGPT backend
                        ▲                                │
                        └────── oai-events datachannel ──┘
   codex app-server (stdio JSON-RPC) brokers signalling only
```

PCMU is negotiated end to end, so Telnyx audio needs no transcoding — the same
property the Realtime `g711_ulaw` path relies on. The bridge decides this from
`INPUT_AUDIO_FORMAT` / `OUTPUT_AUDIO_FORMAT` on the session class, not from
`isinstance` checks.

## Protocol v3 differences

These are the traps that make this more than a model-name swap:

| Realtime API | Protocol v3 |
|---|---|
| `conversation.item.create` | **Does not exist.** Use `session.context.append` / `session.update` |
| `response.function_call_arguments.done` | `delegation.created` |
| `conversation.item.create` (function output) | `delegation.context.append` |
| `input_audio_buffer.speech_started` | `input_audio.started` |
| `conversation.item.input_audio_transcription.delta` | `input_transcript.added` |
| `response.audio_transcript.delta` | `output_transcript.added` |

Two behaviours worth keeping in mind:

- **`turn.done` is not final for the caller.** It can arrive carrying partial
  text, so caller turns are committed on a quiet timer
  (`_TURN_QUIET_SECONDS`) and only the agent side closes on `turn.done`.
- **The thread agent must be told to stand down.** In client-managed handoff
  mode the client executes tools, but the core still routes delegations into
  the Codex thread. Without `_THREAD_NOOP_INSTRUCTIONS` it runs real work in
  the background and quietly burns the subscription budget.

## Failure modes

| Symptom | Cause |
|---|---|
| `CodexAuthError` | No `codex login` on the host. |
| `codex CLI not found` | Not installed, or not on the service PATH. |
| `thread not found` | Stale thread after an app-server restart; retried once. |
| `already active` | Leftover session; stopped and retried once. |
| HTTP 400 on delegated turns | `LIVE_VOICE_THREAD_MODEL` is not valid for a ChatGPT account. |
| Calls fail after ~15–90 min | Subscription voice allowance exhausted. |

## Tests

```bash
uv run pytest tests/services/ai/test_codex_app_server.py \
              tests/services/ai/test_live_voice_agent.py -q
```

The broker tests drive a scripted fake `codex app-server` subprocess, so JSON-RPC
framing, the SDP exchange, auth failure and recovery paths are covered without
the real CLI or a login. The WebRTC peer itself is not exercised — a first real
call still needs a logged-in host.
