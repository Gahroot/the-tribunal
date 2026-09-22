#!/usr/bin/env bash
#
# Prestyj Batch Video Ads — full sales-pipeline end-to-end smoke (orchestrator).
#
# Proves the WHOLE pipe carries one synthetic prospect from ad-library discovery
# to a collected payment, against a locally running backend + the shared local
# Postgres. It exercises the real code at every stage and emits a PASS/FAIL line
# per stage, using .ezcoder/eyes/http.sh to replay the inbound + payment webhooks
# and .ezcoder/eyes/logs.sh to confirm the expected stage logs with no traceback.
#
#   1. discover     ad-library Contact (source='ad_library') in the seeded
#                   Prestyj workspace (Python: ... seed).
#   2. first-touch  autopilot outbound iMessage through the real delivery stack
#                   pointed at an in-process stub relay (Python: ... first-touch).
#   3. inbound      replay the prospect reply into the live webhook with
#                   .ezcoder/eyes/http.sh; assert HTTP 200 + message_id.
#   4. inbound-db   assert the inbound Message landed on the right Conversation
#                   with AI enabled + an assigned agent (Python: verify-inbound).
#   5. ai-reply     drive the real AI sales responder (deterministic draft) and
#                   assert the anchor/close reply was sent (Python: ai-reply).
#   6. close        run the production close tool: open a Stripe Checkout link
#                   for the anchor pack and text it; assert a CallPayment row
#                   (Python: close, Stripe session creation stubbed).
#   7. payment      replay the Stripe checkout.session.completed webhook (signed)
#                   into the live backend with .ezcoder/eyes/http.sh; assert 200.
#   8. paid-db      assert the CallPayment is marked paid (Python: verify-paid).
#   9. logs         confirm handler + responder + payment logs with no traceback.
#
# Usage:
#   scripts/dev/prestyj_sales_e2e_smoke.sh
#
# Environment:
#   BACKEND_URL   Base URL of the running backend (default http://127.0.0.1:8000)
#   BACKEND_LOG   Backend log file to scan (default .ezcoder/eyes/out/backend.log)
#
# Prerequisites (see backend/docs/prestyj_sales_e2e_smoke.md):
#   - make dev.db  (shared local Postgres/Redis)
#   - the Prestyj demo workspace seeded (the smoke seeds it automatically if missing)
#   - a local backend running with mac_relay + Stripe configured in backend/.env:
#       TEXT_MESSAGE_PROVIDER=mac_relay, MAC_RELAY_TOKEN/MAC_RELAY_WEBHOOK_TOKEN,
#       STRIPE_SECRET_KEY (any test value), STRIPE_WEBHOOK_SECRET (any test value)
#     logging to BACKEND_LOG.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export EYES_PROJECT_ROOT="$REPO_ROOT"

EYES="$REPO_ROOT/.ezcoder/eyes"
ARTIFACTS="$REPO_ROOT/.ezcoder/eyes/out/prestyj-sales-e2e"
CONTEXT="$ARTIFACTS/context.json"
INBOUND_PAYLOAD="$ARTIFACTS/inbound_payload.json"
STRIPE_PAYLOAD="$ARTIFACTS/stripe_payload.json"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
BACKEND_LOG="${BACKEND_LOG:-$REPO_ROOT/.ezcoder/eyes/out/backend.log}"
MAC_WEBHOOK_URL="${BACKEND_URL%/}/webhooks/mac-relay/messages"
STRIPE_WEBHOOK_URL="${BACKEND_URL%/}/api/v1/billing/webhook"

GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; NC=$'\033[0m'
FAILED=0

pass() { printf "  ${GREEN}PASS${NC} %s\n" "$1"; }
fail() { printf "  ${RED}FAIL${NC} %s\n" "$1"; FAILED=1; }
step() { printf "\n${BOLD}== %s ==${NC}\n" "$1"; }
die()  { printf "${RED}error:${NC} %s\n" "$1" >&2; exit 1; }

jget()   { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$1" "$2"; }
jok()    { printf '%s' "$1" | python3 -c 'import json,sys; print("yes" if json.load(sys.stdin).get("ok") else "no")'; }
jfield() { printf '%s' "$1" | python3 -c 'import json,sys; v=json.load(sys.stdin).get(sys.argv[1],""); print(v if v is not None else "")' "$2"; }

run_py() {
  ( cd "$REPO_ROOT/backend" && uv run python ../scripts/dev/prestyj_sales_e2e_smoke.py "$@" 2>/dev/null ) | tail -n 1
}

# --- preflight -------------------------------------------------------------
step "preflight: backend reachable at $BACKEND_URL"
ready_json="$("$EYES/http.sh" "${BACKEND_URL%/}/readyz" GET 2>/dev/null || true)"
ready_status="$(printf '%s' "$ready_json" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("status",0))
except Exception: print(0)' 2>/dev/null || echo 0)"
if [ "$ready_status" = "200" ] || [ "$ready_status" = "503" ]; then
  pass "backend responding (/readyz -> $ready_status)"
else
  die "backend not reachable at $BACKEND_URL (/readyz -> $ready_status). Start it: cd backend && uv run uvicorn app.main:app --port 8000 > ../.ezcoder/eyes/out/backend.log 2>&1 (override with BACKEND_URL=...)"
fi

# --- 1. discover -----------------------------------------------------------
step "1. discover: ad-library contact in the Prestyj workspace"
seed_res="$(run_py seed --artifacts-dir "$ARTIFACTS")"
[ "$(jok "$seed_res")" = "yes" ] || die "seed failed: $seed_res"
[ -f "$CONTEXT" ] || die "context.json not written"
[ -f "$INBOUND_PAYLOAD" ] || die "inbound_payload.json not written"
PROVIDER_MESSAGE_ID="$(jget "$CONTEXT" inbound_provider_message_id)"
WEBHOOK_TOKEN="$(jget "$CONTEXT" webhook_token)"
CONTACT_ID="$(jfield "$seed_res" contact_id)"
[ -n "$WEBHOOK_TOKEN" ] || die "no mac_relay webhook token (set MAC_RELAY_WEBHOOK_TOKEN/MAC_RELAY_TOKEN)"
if [ "$(jfield "$seed_res" contact_source)" = "ad_library" ]; then
  pass "ad-library contact ready (id=$CONTACT_ID source=ad_library, agent assigned)"
else
  fail "seeded contact is not source=ad_library: $seed_res"
fi

# --- 2. first-touch --------------------------------------------------------
step "2. first-touch: autopilot outbound iMessage"
ft_res="$(run_py first-touch)"
if [ "$(jok "$ft_res")" = "yes" ]; then
  pass "first-touch delivered through relay (message=$(jfield "$ft_res" message_id))"
else
  fail "first-touch failed: $ft_res"
fi

# --- 3. inbound webhook replay ---------------------------------------------
step "3. inbound: replay prospect reply -> $MAC_WEBHOOK_URL"
post_res="$("$EYES/http.sh" "$MAC_WEBHOOK_URL" POST "@$INBOUND_PAYLOAD" -H "Authorization: Bearer $WEBHOOK_TOKEN")"
http_status="$(printf '%s' "$post_res" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
body_file="$(printf '%s' "$post_res" | python3 -c 'import json,sys; print(json.load(sys.stdin)["body"])')"
webhook_status="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status",""))' "$body_file" 2>/dev/null || echo "")"
webhook_msg_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("message_id",""))' "$body_file" 2>/dev/null || echo "")"
if [ "$http_status" = "200" ] && [ "$webhook_status" = "ok" ]; then
  pass "inbound webhook HTTP 200 (status=ok message_id=${webhook_msg_id:-none})"
else
  fail "inbound webhook HTTP $http_status status='$webhook_status' (body: $body_file)"
fi

# --- 4. inbound persistence ------------------------------------------------
step "4. inbound-db: reply persisted on the conversation"
vi_res="$(run_py verify-inbound --context "$CONTEXT")"
CONVERSATION_ID="$(jfield "$vi_res" conversation_id)"
if [ "$(jok "$vi_res")" = "yes" ]; then
  pass "inbound persisted on conversation=$CONVERSATION_ID (inbound + imessage + ai enabled + agent)"
else
  fail "inbound verification failed: $vi_res"
fi

# --- 5. ai-reply -----------------------------------------------------------
step "5. ai-reply: AI sales responder drafts + sends the anchor/close"
ar_res="$(run_py ai-reply --context "$CONTEXT")"
if [ "$(jok "$ar_res")" = "yes" ]; then
  pass "AI reply sent over iMessage (message=$(jfield "$ar_res" ai_message_id))"
else
  fail "ai-reply failed: $ar_res"
fi

# --- 6. close --------------------------------------------------------------
step "6. close: Stripe checkout link for the anchor pack + text it"
close_res="$(run_py close --artifacts-dir "$ARTIFACTS")"
PAYMENT_ID="$(jfield "$close_res" payment_id)"
if [ "$(jok "$close_res")" = "yes" ]; then
  pass "checkout link created + texted (payment=$PAYMENT_ID pack=$(jfield "$close_res" pack_key) \$$(jfield "$close_res" amount))"
else
  fail "close failed: $close_res"
fi

# --- 7. payment webhook replay ---------------------------------------------
step "7. payment: replay signed Stripe checkout.session.completed -> $STRIPE_WEBHOOK_URL"
if [ -f "$STRIPE_PAYLOAD" ]; then
  sig_res="$(run_py stripe-sig --payload "$STRIPE_PAYLOAD")"
  if [ "$(jok "$sig_res")" = "yes" ]; then
    STRIPE_SIG="$(jfield "$sig_res" header)"
    pay_res="$("$EYES/http.sh" "$STRIPE_WEBHOOK_URL" POST "@$STRIPE_PAYLOAD" -H "Stripe-Signature: $STRIPE_SIG")"
    pay_status="$(printf '%s' "$pay_res" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
    pay_body="$(printf '%s' "$pay_res" | python3 -c 'import json,sys; print(json.load(sys.stdin)["body"])')"
    if [ "$pay_status" = "200" ]; then
      pass "payment webhook HTTP 200"
    else
      fail "payment webhook HTTP $pay_status (expected 200; body: $pay_body). Is STRIPE_WEBHOOK_SECRET set on the backend?"
    fi
  else
    fail "could not sign Stripe payload: $sig_res (set STRIPE_WEBHOOK_SECRET in backend/.env)"
  fi
else
  fail "stripe_payload.json missing — close stage did not create a CallPayment"
fi

# --- 8. payment reconciliation ---------------------------------------------
step "8. paid-db: CallPayment marked paid"
vp_res="$(run_py verify-paid --context "$CONTEXT")"
if [ "$(jok "$vp_res")" = "yes" ]; then
  pass "payment reconciled (status=$(jfield "$vp_res" status) amount=\$$(jfield "$vp_res" amount))"
else
  fail "payment not marked paid: $vp_res"
fi

# --- 9. logs ---------------------------------------------------------------
step "9. logs: handler + responder + payment, no traceback"
if [ -f "$BACKEND_LOG" ]; then
  scope="$("$EYES/logs.sh" --file "$BACKEND_LOG" --lines 8000 \
    --grep "$PROVIDER_MESSAGE_ID|mac_relay_handler_failed|mac_relay_inbound_processed|stripe_webhook_received|call_payment_marked_paid|${CONVERSATION_ID:-__no_conv__}" 2>/dev/null || true)"
  if printf '%s' "$scope" | grep -q "mac_relay_inbound_processed"; then
    pass "handler logged mac_relay_inbound_processed"
  else
    fail "no mac_relay_inbound_processed for $PROVIDER_MESSAGE_ID in $BACKEND_LOG"
  fi
  if printf '%s' "$scope" | grep -q "call_payment_marked_paid"; then
    pass "webhook logged call_payment_marked_paid"
  else
    fail "no call_payment_marked_paid log line in $BACKEND_LOG"
  fi
  if printf '%s' "$scope" | grep -q "mac_relay_handler_failed"; then
    fail "webhook handler logged mac_relay_handler_failed (traceback in handler path)"
  else
    pass "no mac_relay_handler_failed in handler path"
  fi
else
  fail "backend log not found at $BACKEND_LOG (set BACKEND_LOG=...)"
fi

# --- summary ---------------------------------------------------------------
step "summary"
if [ "$FAILED" -eq 0 ]; then
  printf "${GREEN}${BOLD}Prestyj sales pipeline OK — discover -> first-touch -> reply -> AI -> close -> paid.${NC}\n"
  printf "${DIM}artifacts: %s${NC}\n" "$ARTIFACTS"
  exit 0
else
  printf "${RED}${BOLD}Prestyj sales E2E smoke FAILED.${NC} See failures above.\n"
  printf "${DIM}artifacts: %s ; backend log: %s${NC}\n" "$ARTIFACTS" "$BACKEND_LOG"
  exit 1
fi
