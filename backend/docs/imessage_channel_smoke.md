# iMessage channel smoke check

The Tribunal runs the Prestyj Batch Video Ads sales department autonomously over
iMessage. Every part of that autonomy — discover, first-touch, objection-handle,
anchor-close, Stripe handoff — depends on the self-hosted Mac iMessage relay
working in **both** directions. This smoke check is the repeatable "is the pipe
open?" proof for that channel.

It exercises the real code paths:

- **Outbound:** `OutboundDeliveryService.deliver(...)` with
  `OutboundDeliveryChannel.IMESSAGE` → `MacRelayMessageService`
  (`app/services/telephony/mac_relay.py`) → HTTP `POST /v1/messages` to the relay.
- **Inbound:** relay webhook `POST /webhooks/mac-relay/messages`
  (`app/api/webhooks/mac_relay.py` + `mac_relay_handlers.py`) → inbound text
  pipeline (`app/services/telephony/inbound_text.py`) → `Conversation` + AI
  responder scheduling (`app/services/ai/text_agent.schedule_ai_response`).

## What it asserts

1. **Outbound** — an iMessage sent through the delivery stack is accepted by the
   relay (a stub relay captures the exact `POST /v1/messages` body), persists a
   `Message` with `channel=imessage`, `direction=outbound`, and a
   `mac-relay:`-prefixed `provider_message_id`.
2. **Inbound webhook** — replaying a minimal inbound event returns HTTP `200`
   with `status=ok` and a `message_id`.
3. **Inbound persistence** — the inbound `Message` lands on the right
   `Conversation` (matching sender identity + contact), with `channel=imessage`,
   `direction=inbound`, AI enabled and not paused, and an assigned agent.
4. **Handling + responder** — the backend log shows `mac_relay_inbound_processed`
   and `ai_response_scheduled` for that conversation, with **no**
   `mac_relay_handler_failed` (no traceback) in the handler path.

## Files

- `scripts/dev/imessage_channel_smoke.sh` — orchestrator (preflight → seed →
  outbound → webhook replay → verify → logs). Prints PASS/FAIL and exits
  non-zero on failure.
- `scripts/dev/imessage_channel_smoke.py` — Python worker with subcommands
  (`seed`, `outbound`, `verify-inbound`). Each prints one JSON result line.
- Artifacts (gitignored) under `.ezcoder/eyes/out/imessage-smoke/`:
  - `payload.json` — the inbound webhook body replayed with `.ezcoder/eyes/http.sh`.
  - `context.json` — seeded ids, the sender identity, and the relay webhook token.

The check seeds a dedicated, idempotent **`imessage-smoke`** workspace (sender
identity, agent, contact) so it never touches real CRM data and is safe to
re-run.

## Prerequisites

1. **Local Postgres + Redis** (the shared local stack):

   ```bash
   make dev.db
   ```

2. **Backend running with the relay configured.** `backend/.env` should have:

   ```ini
   TEXT_MESSAGE_PROVIDER=mac_relay
   MAC_RELAY_BASE_URL=http://127.0.0.1:8765
   MAC_RELAY_TOKEN=<shared relay token>
   MAC_RELAY_WEBHOOK_TOKEN=<webhook bearer token>   # falls back to MAC_RELAY_TOKEN
   ```

   Start the backend so it writes logs to a file the check can read. The default
   log path is `.ezcoder/eyes/out/backend.log`:

   ```bash
   cd backend
   uv run uvicorn app.main:app --port 8000 > ../.ezcoder/eyes/out/backend.log 2>&1
   ```

   > The outbound leg does **not** require a real Mac relay daemon — the check
   > spins up an in-process stub relay and points the (process-local) settings
   > at it. A live daemon (`scripts/ops/mac_imessage_relay.py`) is only needed to
   > deliver to an actual device.

## Run it

```bash
scripts/dev/imessage_channel_smoke.sh
```

Environment overrides:

| Variable      | Default                                  | Purpose |
|---------------|------------------------------------------|---------|
| `BACKEND_URL` | `http://127.0.0.1:8000`                  | Base URL of the running backend. |
| `BACKEND_LOG` | `<repo>/.ezcoder/eyes/out/backend.log`   | Log file the responder writes to, scanned in step 5. |

Example against a backend on another port:

```bash
BACKEND_URL=http://127.0.0.1:8010 scripts/dev/imessage_channel_smoke.sh
```

Expected output ends with:

```
iMessage channel OK — both directions verified.
```

## Run pieces manually

```bash
cd backend

# 1. Seed + write artifacts
uv run python ../scripts/dev/imessage_channel_smoke.py seed \
  --artifacts-dir ../.ezcoder/eyes/out/imessage-smoke

# 2. Outbound through the stub relay
uv run python ../scripts/dev/imessage_channel_smoke.py outbound

# 3. Replay the inbound webhook (token + url from context.json)
TOKEN=$(python3 -c "import json;print(json.load(open('../.ezcoder/eyes/out/imessage-smoke/context.json'))['webhook_token'])")
../.ezcoder/eyes/http.sh http://127.0.0.1:8000/webhooks/mac-relay/messages \
  POST @../.ezcoder/eyes/out/imessage-smoke/payload.json \
  -H "Authorization: Bearer $TOKEN"

# 4. Verify inbound persistence
uv run python ../scripts/dev/imessage_channel_smoke.py verify-inbound \
  --context ../.ezcoder/eyes/out/imessage-smoke/context.json

# 5. Confirm handling + responder in the log
../.ezcoder/eyes/logs.sh --file "$PWD/../.ezcoder/eyes/out/backend.log" --lines 5000 \
  --grep "mac_relay_inbound_processed|ai_response_scheduled|mac_relay_handler_failed"
```

## Notes & gotchas

- **`no_openai_credential` is expected** in local logs when `OPENAI_API_KEY` is
  empty — the AI responder still *fires* (`processing_inbound_with_ai`), which is
  what we assert. It just can't draft a reply without a key. Set the key to see
  an actual outbound AI response.
- **Sender identity is a phone number**, not an Apple ID email, because
  `conversations.workspace_phone` is `VARCHAR(20)` and an email overflows it. The
  relay supports email senders for real devices; the smoke check uses a phone
  identity to stay schema-safe.
- **Idempotency** is part of the proof: replaying the same webhook a second time
  returns `{"status": "ok", "reason": "duplicate"}` and does not double-persist.
- The log scan is **scoped to this request** (by `provider_message_id` and the
  seeded `conversation_id`), so unrelated background-worker tracebacks in the
  shared log don't fail the check — only a `mac_relay_handler_failed` in the
  webhook path does.
