# Prestyj sales full-pipeline E2E smoke

The Tribunal autonomously runs the entire Prestyj Batch Video Ads sales
department over iMessage: discover → first-touch → objection-handle →
anchor-close → Stripe payment → operator report. This smoke proves the **whole
pipe** carries one synthetic prospect from ad-library discovery all the way to a
collected payment, against a locally running backend + the shared local
Postgres. It emits a **PASS/FAIL per stage** and exits non-zero on any failure.

It exercises the real code paths (nothing about the pipeline is re-implemented):

- **Discover** — an ad-library `Contact` (`source='ad_library'`) in the seeded
  `prestyj-batch-video-ads-demo` workspace.
- **First-touch** — `OutboundDeliveryService.deliver(...)` with
  `OutboundDeliveryChannel.IMESSAGE` → `MacRelayMessageService`
  (`app/services/telephony/mac_relay.py`) → HTTP `POST /v1/messages`.
- **Inbound** — relay webhook `POST /webhooks/mac-relay/messages`
  (`app/api/webhooks/mac_relay.py` + `mac_relay_handlers.py`) → inbound text
  pipeline (`app/services/telephony/inbound_text.py`) → `Conversation`.
- **AI reply** — the real text responder
  (`app/services/ai/text_agent.process_inbound_with_ai`), including human-like
  timing, trace persistence, and the mac_relay transport.
- **Close** — the production close tool
  (`app/services/ai/crm_assistant/_payment_tools.PaymentAssistantTools`) →
  `app/services/payments/call_payment_service.create_payment_checkout_session`,
  persisting a `CallPayment` and texting the link over iMessage.
- **Payment** — the shared Stripe webhook (`POST /api/v1/billing/webhook`) →
  `call_payment_service.handle_checkout_session_completed` marks the
  `CallPayment` paid and notifies operators.

## What it asserts (PASS/FAIL per stage)

1. **discover** — the synthetic ad-library `Contact` exists with
   `source='ad_library'` and the iMessage sender has an assigned agent.
2. **first-touch** — an autopilot outbound iMessage is accepted by the relay
   (an in-process stub relay captures the exact `POST /v1/messages` body) and a
   `Message` is persisted with `channel=imessage`, `direction=outbound`, and a
   `mac-relay:`-prefixed `provider_message_id`.
3. **inbound** — replaying the prospect's reply returns HTTP `200`
   with `status=ok` and a `message_id`.
4. **inbound-db** — the inbound `Message` lands on the right `Conversation`
   (matching sender identity + contact, linked to the contact), with
   `channel=imessage`, `direction=inbound`, AI enabled, and an assigned agent.
5. **ai-reply** — the AI responder drafts and sends the anchor/close reply over
   iMessage (asserted as a new outbound `Message` + a relay send).
6. **close** — a `CallPayment` row is created (`pending`) for the **anchor
   pack** (`anchor_500`, $2,500), the Stripe session id + checkout URL are
   recorded, and a checkout link is texted over iMessage.
7. **payment** — replaying a **signed** `checkout.session.completed` event
   returns HTTP `200`.
8. **paid-db** — the `CallPayment` is `paid`, `paid_at` is set, the payment
   intent is recorded, and operators were notified.
9. **logs** — the backend log shows `mac_relay_inbound_processed` and
   `call_payment_marked_paid`, with **no** `mac_relay_handler_failed`
   (no traceback) in the handler path.

## Stubbing strategy

The smoke is deterministic and self-contained — it never touches a real Mac
device, a live relay daemon, or the real Stripe API:

- The **outbound relay HTTP boundary** is an in-process stub relay; the
  (process-local) `mac_relay_*` settings are pointed at it for the duration of
  each outbound leg. The full outbound stack runs unchanged.
- The **OpenAI completion** in the ai-reply stage is replaced with a
  deterministic anchor-close draft (`generate_text_response` +
  `get_openai_bearer_token` are patched). The rest of the responder is the real
  production path.
- The **Stripe Checkout Session creation** is stubbed to return a deterministic
  session id + URL. `CallPayment` persistence, metadata, and iMessage delivery
  run through real code. The **payment-reconcile webhook is replayed against the
  live backend with a genuinely signed payload** (HMAC over
  `STRIPE_WEBHOOK_SECRET`), so signature verification + routing + reconciliation
  are all real.

The smoke seeds a dedicated synthetic prospect (`contact_id=9980001`,
`+13105550148`) and resets its conversation/messages/payments on each run, so it
never collides with the 20 seeded ad-library advertisers and is safe to re-run.

## Files

- `scripts/dev/prestyj_sales_e2e_smoke.sh` — orchestrator (preflight → seed →
  first-touch → webhook replay → verify → ai-reply → close → payment webhook →
  verify → logs). Prints PASS/FAIL and exits non-zero on failure.
- `scripts/dev/prestyj_sales_e2e_smoke.py` — Python worker with subcommands
  (`seed`, `first-touch`, `verify-inbound`, `ai-reply`, `close`, `stripe-sig`,
  `verify-paid`). Each prints one JSON result line.
- Artifacts (gitignored) under `.ezcoder/eyes/out/prestyj-sales-e2e/`:
  - `inbound_payload.json` — the inbound relay webhook body.
  - `stripe_payload.json` — the `checkout.session.completed` event body.
  - `context.json` — seeded ids, sender identity, and the relay webhook token.

## Prerequisites

1. **Local Postgres + Redis** (the shared local stack):

   ```bash
   make dev.db
   ```

2. **The Prestyj demo workspace seeded.** The smoke seeds it automatically if
   missing, but you can seed it explicitly:

   ```bash
   cd backend && uv run python -m scripts.seed_prestyj
   ```

3. **Backend running with mac_relay + Stripe configured** in `backend/.env`:

   ```ini
   TEXT_MESSAGE_PROVIDER=mac_relay
   MAC_RELAY_BASE_URL=http://127.0.0.1:8765
   MAC_RELAY_TOKEN=<shared relay token>
   MAC_RELAY_WEBHOOK_TOKEN=<webhook bearer token>   # falls back to MAC_RELAY_TOKEN
   STRIPE_SECRET_KEY=sk_test_...                     # any test value; Stripe is stubbed
   STRIPE_WEBHOOK_SECRET=whsec_...                   # used to sign the replayed webhook
   ```

   Start the backend so it writes to a log file the check can read (default
   `.ezcoder/eyes/out/backend.log`). Disable in-process workers to keep the log
   focused:

   ```bash
   cd backend
   RUN_BACKGROUND_WORKERS=false uv run uvicorn app.main:app --port 8000 \
     > ../.ezcoder/eyes/out/backend.log 2>&1
   ```

   > The smoke does **not** require a real Mac relay daemon — the outbound legs
   > use an in-process stub relay. Nor does it require real Stripe — session
   > creation is stubbed and only the webhook signature uses the secret.

## Run it

```bash
scripts/dev/prestyj_sales_e2e_smoke.sh
```

Environment overrides:

| Variable      | Default                                  | Purpose |
|---------------|------------------------------------------|---------|
| `BACKEND_URL` | `http://127.0.0.1:8000`                  | Base URL of the running backend. |
| `BACKEND_LOG` | `<repo>/.ezcoder/eyes/out/backend.log`   | Log file scanned in the logs stage. |

Example against a backend on another port:

```bash
BACKEND_URL=http://127.0.0.1:8011 scripts/dev/prestyj_sales_e2e_smoke.sh
```

Expected output ends with:

```
Prestyj sales pipeline OK — discover -> first-touch -> reply -> AI -> close -> paid.
```

## Run pieces manually

```bash
cd backend
ART=../.ezcoder/eyes/out/prestyj-sales-e2e

# 1. discover + write artifacts
uv run python ../scripts/dev/prestyj_sales_e2e_smoke.py seed --artifacts-dir "$ART"

# 2. first-touch through the stub relay
uv run python ../scripts/dev/prestyj_sales_e2e_smoke.py first-touch

# 3. replay the inbound reply (token from context.json)
TOKEN=$(python3 -c "import json;print(json.load(open('$ART/context.json'))['webhook_token'])")
../.ezcoder/eyes/http.sh http://127.0.0.1:8000/webhooks/mac-relay/messages \
  POST @"$ART/inbound_payload.json" -H "Authorization: Bearer $TOKEN"

# 4. verify inbound + 5. drive the AI reply
uv run python ../scripts/dev/prestyj_sales_e2e_smoke.py verify-inbound --context "$ART/context.json"
uv run python ../scripts/dev/prestyj_sales_e2e_smoke.py ai-reply --context "$ART/context.json"

# 6. close (writes stripe_payload.json)
uv run python ../scripts/dev/prestyj_sales_e2e_smoke.py close --artifacts-dir "$ART"

# 7. sign + replay the payment webhook
SIG=$(uv run python ../scripts/dev/prestyj_sales_e2e_smoke.py stripe-sig --payload "$ART/stripe_payload.json" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["header"])')
../.ezcoder/eyes/http.sh http://127.0.0.1:8000/api/v1/billing/webhook \
  POST @"$ART/stripe_payload.json" -H "Stripe-Signature: $SIG"

# 8. verify the payment was reconciled
uv run python ../scripts/dev/prestyj_sales_e2e_smoke.py verify-paid --context "$ART/context.json"
```

## Notes & gotchas

- **Sender identity is the demo phone number** (`+18885550197`), not the Apple
  ID-style `mac_relay_sender_id`, because the outbound relay normalizes the
  sender as a phone/email and `conversations.workspace_phone` is `VARCHAR(20)`.
  The seed step pins `PhoneNumber.mac_relay_sender_id` to the phone so inbound →
  conversation → outbound all resolve to one coherent thread.
- The **texted checkout link is a tracked short link**, not the raw Stripe URL —
  the unified delivery stack rewrites it. The exact Stripe URL is preserved on
  `CallPayment.payment_link_url`, which the close stage asserts.
- **Idempotency** is real: the payment webhook handler marks the `CallPayment`
  paid exactly once and guards operator notification with
  `operators_notified_at`.
- The log scan is **scoped** by `provider_message_id` and the conversation id,
  so unrelated background-worker tracebacks in a shared log don't fail the check.
```
