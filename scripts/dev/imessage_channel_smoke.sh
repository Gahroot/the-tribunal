#!/usr/bin/env bash
#
# iMessage channel bidirectional smoke check (orchestrator).
#
# Proves the self-hosted Mac iMessage relay path works in BOTH directions
# against a locally running backend + the shared local Postgres. All of The
# Tribunal's sales autonomy rides on this channel, so this is the repeatable
# "is the pipe open?" check.
#
#   1. seed      - create a dedicated smoke workspace/sender/agent/contact and
#                  write payload.json + context.json artifacts.
#   2. outbound  - send an outbound iMessage through the real delivery stack
#                  pointed at an in-process stub relay; assert it was delivered
#                  and persisted (Python: imessage_channel_smoke.py outbound).
#   3. inbound   - replay payload.json into the live webhook with
#                  .ezcoder/eyes/http.sh and assert HTTP 200 + message_id.
#   4. verify    - assert the inbound Message landed on the right Conversation
#                  with AI enabled (Python: ... verify-inbound).
#   5. logs      - confirm in .ezcoder/eyes/logs.sh that the handler processed
#                  the message and the AI responder fired, with no handler
#                  traceback scoped to this request.
#
# Usage:
#   scripts/dev/imessage_channel_smoke.sh
#
# Environment:
#   BACKEND_URL   Base URL of the running backend (default http://127.0.0.1:8000)
#   BACKEND_LOG   Path to the backend log file the responder writes to
#                 (default <repo>/.ezcoder/eyes/out/backend.log)
#
# Prerequisites: a local backend running with the mac_relay env configured
# (TEXT_MESSAGE_PROVIDER=mac_relay, MAC_RELAY_* set in backend/.env) and logging
# to BACKEND_LOG, plus the local Postgres/Redis from `make dev.db`. See
# backend/docs/imessage_channel_smoke.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export EYES_PROJECT_ROOT="$REPO_ROOT"

EYES="$REPO_ROOT/.ezcoder/eyes"
ARTIFACTS="$REPO_ROOT/.ezcoder/eyes/out/imessage-smoke"
CONTEXT="$ARTIFACTS/context.json"
PAYLOAD="$ARTIFACTS/payload.json"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
BACKEND_LOG="${BACKEND_LOG:-$REPO_ROOT/.ezcoder/eyes/out/backend.log}"
WEBHOOK_URL="${BACKEND_URL%/}/webhooks/mac-relay/messages"

GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; NC=$'\033[0m'
FAILED=0

pass() { printf "  ${GREEN}PASS${NC} %s\n" "$1"; }
fail() { printf "  ${RED}FAIL${NC} %s\n" "$1"; FAILED=1; }
step() { printf "\n${BOLD}== %s ==${NC}\n" "$1"; }
die()  { printf "${RED}error:${NC} %s\n" "$1" >&2; exit 1; }

# Read a top-level string field from a JSON file.
jget() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$1" "$2"; }
# Read .ok from a one-line JSON result string.
jok()  { printf '%s' "$1" | python3 -c 'import json,sys; print("yes" if json.load(sys.stdin).get("ok") else "no")'; }
# Read an arbitrary field from a one-line JSON result string: jfield <json> <field>.
jfield() { printf '%s' "$1" | python3 -c 'import json,sys; v=json.load(sys.stdin).get(sys.argv[1],""); print(v if v is not None else "")' "$2"; }

run_py() {
  # Runs a smoke subcommand from the backend dir and echoes its last (JSON) line.
  ( cd "$REPO_ROOT/backend" && uv run python ../scripts/dev/imessage_channel_smoke.py "$@" 2>/dev/null ) | tail -n 1
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
  die "backend not reachable at $BACKEND_URL (/readyz -> $ready_status). Start it, e.g.: cd backend && uv run uvicorn app.main:app --port 8000  (override with BACKEND_URL=...)"
fi

# --- 1. seed ---------------------------------------------------------------
step "1. seed workspace / sender / agent / contact"
seed_res="$(run_py seed --artifacts-dir "$ARTIFACTS")"
[ "$(jok "$seed_res")" = "yes" ] || die "seed failed: $seed_res"
[ -f "$CONTEXT" ] || die "context.json not written"
[ -f "$PAYLOAD" ] || die "payload.json not written"
PROVIDER_MESSAGE_ID="$(jget "$CONTEXT" inbound_provider_message_id)"
WEBHOOK_TOKEN="$(jget "$CONTEXT" webhook_token)"
SENDER="$(jget "$CONTEXT" sender)"
[ -n "$WEBHOOK_TOKEN" ] || die "no mac_relay webhook token in context (set MAC_RELAY_WEBHOOK_TOKEN/MAC_RELAY_TOKEN in backend/.env)"
pass "seeded sender=$SENDER provider_message_id=$PROVIDER_MESSAGE_ID"

# --- 2. outbound (through the relay) --------------------------------------
step "2. outbound iMessage through the relay"
out_res="$(run_py outbound)"
if [ "$(jok "$out_res")" = "yes" ]; then
  pass "outbound delivered ($(jfield "$out_res" provider_message_id))"
else
  fail "outbound send failed: $out_res"
fi

# --- 3. inbound webhook replay --------------------------------------------
step "3. replay inbound webhook -> $WEBHOOK_URL"
post_res="$("$EYES/http.sh" "$WEBHOOK_URL" POST "@$PAYLOAD" -H "Authorization: Bearer $WEBHOOK_TOKEN")"
http_status="$(printf '%s' "$post_res" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
body_file="$(printf '%s' "$post_res" | python3 -c 'import json,sys; print(json.load(sys.stdin)["body"])')"
webhook_status="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status",""))' "$body_file" 2>/dev/null || echo "")"
webhook_msg_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("message_id",""))' "$body_file" 2>/dev/null || echo "")"
if [ "$http_status" = "200" ]; then
  pass "webhook returned HTTP 200 (status=$webhook_status message_id=${webhook_msg_id:-none})"
else
  fail "webhook returned HTTP $http_status (expected 200); body: $body_file"
fi
[ "$webhook_status" = "ok" ] || fail "webhook body status was '$webhook_status' (expected 'ok')"

# --- 4. verify inbound persistence ----------------------------------------
step "4. verify inbound message landed on the right conversation"
verify_res="$(run_py verify-inbound --context "$CONTEXT")"
CONVERSATION_ID="$(jfield "$verify_res" conversation_id)"
if [ "$(jok "$verify_res")" = "yes" ]; then
  pass "inbound persisted on conversation=$CONVERSATION_ID (inbound + imessage + ai enabled)"
else
  fail "inbound verification failed: $verify_res"
fi

# --- 5. logs: handler + responder, no handler traceback -------------------
step "5. confirm handling + AI responder in backend logs"
if [ -f "$BACKEND_LOG" ]; then
  log_scope="$("$EYES/logs.sh" --file "$BACKEND_LOG" --lines 5000 \
    --grep "$PROVIDER_MESSAGE_ID|mac_relay_handler_failed|${CONVERSATION_ID:-__no_conv__}" 2>/dev/null || true)"

  if printf '%s' "$log_scope" | grep -q "mac_relay_inbound_processed"; then
    pass "handler logged mac_relay_inbound_processed (message persisted, no handler error)"
  else
    fail "no mac_relay_inbound_processed log line for $PROVIDER_MESSAGE_ID in $BACKEND_LOG"
  fi

  if [ -n "$CONVERSATION_ID" ] && printf '%s' "$log_scope" | grep -q "ai_response_scheduled"; then
    pass "AI responder fired (ai_response_scheduled for $CONVERSATION_ID)"
  else
    fail "no ai_response_scheduled log line for conversation $CONVERSATION_ID"
  fi

  if printf '%s' "$log_scope" | grep -q "mac_relay_handler_failed"; then
    fail "webhook handler logged mac_relay_handler_failed (traceback in handler path)"
  else
    pass "no mac_relay_handler_failed in handler path (no webhook traceback)"
  fi
else
  fail "backend log not found at $BACKEND_LOG (set BACKEND_LOG=... to the file the backend writes to)"
fi

# --- summary ---------------------------------------------------------------
step "summary"
if [ "$FAILED" -eq 0 ]; then
  printf "${GREEN}${BOLD}iMessage channel OK — both directions verified.${NC}\n"
  printf "${DIM}artifacts: %s${NC}\n" "$ARTIFACTS"
  exit 0
else
  printf "${RED}${BOLD}iMessage channel smoke check FAILED.${NC} See failures above.\n"
  printf "${DIM}artifacts: %s ; backend log: %s${NC}\n" "$ARTIFACTS" "$BACKEND_LOG"
  exit 1
fi
