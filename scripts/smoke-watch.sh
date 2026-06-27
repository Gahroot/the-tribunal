#!/usr/bin/env bash
#
# smoke-watch.sh — continuously verify a live deployment, step by step.
#
# Re-runs an ordered list of liveness checks against a running backend and
# frontend on an interval and prints a ✓/✗ line per step every cycle. Unlike
# the pytest/Playwright smoke suites (post-deploy gates that spin up a process
# or a browser), this is a lightweight curl-only heartbeat meant to run for
# long stretches against `make dev` or a remote environment.
#
# Usage:
#   scripts/smoke-watch.sh                 # loop forever, 15s interval, local URLs
#   scripts/smoke-watch.sh --once          # single pass, exit non-zero on any failure
#   scripts/smoke-watch.sh --interval 30   # custom interval (seconds)
#
# Env overrides:
#   BACKEND_URL   (default http://127.0.0.1:8000)
#   FRONTEND_URL  (default http://127.0.0.1:3000)
#   INTERVAL      (default 15)            # seconds between cycles
#
# The steps mirror backend/tests/smoke/test_deployment_smoke.py and
# frontend/e2e/smoke.spec.ts so this dashboard and the CI gates agree on what
# "healthy" means.
set -uo pipefail

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:3000}"
INTERVAL="${INTERVAL:-15}"
ONCE=0
REQUEST_TIMEOUT=10

while [ $# -gt 0 ]; do
  case "$1" in
    --once) ONCE=1; shift ;;
    --interval) INTERVAL="${2:?--interval needs a value}"; shift 2 ;;
    --backend) BACKEND_URL="${2:?--backend needs a URL}"; shift 2 ;;
    --frontend) FRONTEND_URL="${2:?--frontend needs a URL}"; shift 2 ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Colors only when attached to a terminal (keeps background logs clean).
if [ -t 1 ]; then
  GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  GREEN=''; RED=''; DIM=''; BOLD=''; RESET=''
fi

BASES_DOWN_HINT="is the dev server up? (make dev)"

# Per-cycle counters, reset at the top of each cycle.
PASS=0
FAIL=0

# step <name> <command...> — run a predicate, print a ✓/✗ line, tally result.
# The command must return 0 for pass, non-zero for fail. stderr from the
# command is captured and shown inline on failure.
step() {
  local name="$1"; shift
  local err
  if err=$("$@" 2>&1); then
    printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$name"
    PASS=$((PASS + 1))
  else
    printf '  %s✗ %s%s %s%s%s\n' "$RED" "$name" "$RESET" "$DIM" "${err:-failed}" "$RESET"
    FAIL=$((FAIL + 1))
  fi
}

# --- predicates ------------------------------------------------------------
# Each echoes a short reason to stderr and returns non-zero on failure.

# Fetch a URL once; sets globals HTTP_CODE and HTTP_BODY. Returns non-zero if
# the request itself could not be made (connection refused, timeout, DNS).
_fetch() {
  local url="$1" resp
  if ! resp=$(curl -sS -m "$REQUEST_TIMEOUT" -w $'\n%{http_code}' "$url" 2>/dev/null); then
    HTTP_CODE="000"; HTTP_BODY=""
    return 1
  fi
  HTTP_CODE="${resp##*$'\n'}"
  HTTP_BODY="${resp%$'\n'*}"
  return 0
}

expect_status() {
  local url="$1" want="$2"
  if ! _fetch "$url"; then
    echo "unreachable — $BASES_DOWN_HINT"
    return 1
  fi
  if [ "$HTTP_CODE" != "$want" ]; then
    echo "got HTTP $HTTP_CODE, want $want"
    return 1
  fi
}

backend_livez() {
  expect_status "$BACKEND_URL/livez" 200 || return 1
  jq -e '.status == "ok"' <<<"$HTTP_BODY" >/dev/null 2>&1 || { echo "status != ok"; return 1; }
}

backend_readyz() {
  expect_status "$BACKEND_URL/readyz" 200 || return 1
  if ! jq -e '.status == "ok" and ([.checks[].ok] | all)' <<<"$HTTP_BODY" >/dev/null 2>&1; then
    local bad
    bad=$(jq -r '[.checks | to_entries[] | select(.value.ok == false) | .key] | join(", ")' <<<"$HTTP_BODY" 2>/dev/null)
    echo "unhealthy: ${bad:-unknown}"
    return 1
  fi
}

backend_version() {
  expect_status "$BACKEND_URL/version" 200 || return 1
  jq -e '.sha != null and .sha != ""' <<<"$HTTP_BODY" >/dev/null 2>&1 || { echo "missing sha"; return 1; }
}

backend_auth_enforced() {
  expect_status "$BACKEND_URL/api/v1/auth/me" 401
}

backend_security_headers() {
  local headers
  if ! headers=$(curl -sS -m "$REQUEST_TIMEOUT" -D - -o /dev/null "$BACKEND_URL/livez" 2>/dev/null); then
    echo "unreachable — $BASES_DOWN_HINT"
    return 1
  fi
  grep -qi '^X-Content-Type-Options: *nosniff' <<<"$headers" || { echo "missing X-Content-Type-Options"; return 1; }
  grep -qi '^X-Frame-Options: *DENY' <<<"$headers" || { echo "missing X-Frame-Options"; return 1; }
  grep -qi '^Strict-Transport-Security:' <<<"$headers" || { echo "missing Strict-Transport-Security"; return 1; }
}

frontend_root() {
  if ! _fetch "$FRONTEND_URL/"; then
    echo "unreachable — $BASES_DOWN_HINT"
    return 1
  fi
  if [ "$HTTP_CODE" -ge 400 ] 2>/dev/null; then
    echo "got HTTP $HTTP_CODE"
    return 1
  fi
}

frontend_login() {
  local ctype
  expect_status "$FRONTEND_URL/login" 200 || return 1
  ctype=$(curl -sS -m "$REQUEST_TIMEOUT" -o /dev/null -w '%{content_type}' "$FRONTEND_URL/login" 2>/dev/null)
  case "$ctype" in
    text/html*) : ;;
    *) echo "content-type '$ctype' is not HTML"; return 1 ;;
  esac
}

run_cycle() {
  PASS=0
  FAIL=0
  printf '%s[%s]%s backend=%s frontend=%s\n' \
    "$DIM" "$(date '+%H:%M:%S')" "$RESET" "$BACKEND_URL" "$FRONTEND_URL"

  printf '%sbackend%s\n' "$BOLD" "$RESET"
  step "livez — process up"               backend_livez
  step "readyz — deps + workers healthy"  backend_readyz
  step "version — build sha served"       backend_version
  step "auth — protected route is 401"    backend_auth_enforced
  step "security headers present"         backend_security_headers

  printf '%sfrontend%s\n' "$BOLD" "$RESET"
  step "root — app served (<400)"         frontend_root
  step "login — html shell served"        frontend_login

  local total=$((PASS + FAIL))
  if [ "$FAIL" -eq 0 ]; then
    printf '%s→ %d/%d passed%s\n\n' "$GREEN" "$PASS" "$total" "$RESET"
  else
    printf '%s→ %d/%d passed, %d FAILED%s\n\n' "$RED" "$PASS" "$total" "$FAIL" "$RESET"
  fi
}

if [ "$ONCE" -eq 1 ]; then
  run_cycle
  [ "$FAIL" -eq 0 ]
  exit $?
fi

printf '%ssmoke-watch%s — every %ss, Ctrl-C to stop\n\n' "$BOLD" "$RESET" "$INTERVAL"
while true; do
  run_cycle
  sleep "$INTERVAL"
done
