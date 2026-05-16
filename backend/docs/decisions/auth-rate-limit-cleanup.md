# Auth rate-limit storage: keep Postgres, add a cleanup worker

**Date:** 2026-05-15
**Status:** Accepted

## Context

`app/models/auth_rate_limit.py` (`auth_rate_limits` table) is append-only. Every
authentication attempt — login, register, refresh, plus a per-failure row for
the username lockout — inserts a row. The IP rate limiter and the username
lockout both read this table on every auth request:

```python
# app/api/v1/auth.py
window_start = datetime.now(UTC) - timedelta(minutes=_AUTH_RATE_WINDOW_MINUTES)
select(func.count()).where(
    AuthRateLimit.client_ip == client_ip,
    AuthRateLimit.endpoint == endpoint,
    AuthRateLimit.created_at >= window_start,
)
```

Without pruning the table grows unbounded. The composite index
`ix_auth_rate_limits_client_ip_created_at` keeps the count fast for now, but
unbounded growth eventually hurts vacuum, autovacuum thresholds, backup size,
and any sequential fallback.

Two options were on the table:

1. **DB cleanup worker.** Hourly delete of rows older than 24h.
2. **Move to Redis.** Sliding window via `INCR` + `EXPIRE` per
   (endpoint, ip) and (endpoint, username_hash) key. Redis is already used
   for outbound rate limits (`services/rate_limiting/rate_limiter.py`),
   number pool, opt-outs, reputation, warming.

## Decision

**Option 1: keep Postgres, add `AuthRateLimitCleanupWorker`.**

The worker (`app/workers/auth_rate_limit_cleanup_worker.py`) runs hourly and
deletes rows older than `RETENTION_HOURS = 24`. Registered in
`ALL_REGISTRIES` so it starts with every other worker via the FastAPI
`lifespan` hook in `app/main.py`.

## Why not Redis

Redis would arguably be a better steady-state design — naturally TTL'd,
zero cleanup burden, lower write amplification. But this is a live CRM with
real users, and the auth path is security-critical. The migration cost vs.
benefit is poor right now:

- **Blast radius.** Every auth request reads and writes the limiter. A bug
  in the migration locks users out or, worse, silently disables the
  limiter. The current implementation works.
- **Lockout semantics.** The username lockout in `_check_username_lockout`
  uses the same table to enforce a per-username failure cap across IPs.
  Redis would need two parallel key namespaces (per-IP and per-username)
  with matching atomic increment-and-check semantics. Doable, but a real
  change to the auth surface.
- **Audit trail.** The DB rows give us forensics during incidents
  (e.g. "show me every failed login from this IP in the last hour"). Redis
  counters lose that — gone the moment the window expires.
- **Test surface.** Existing tests
  (`tests/api/test_auth_username_lockout.py`) assert on `AuthRateLimit`
  rows added to the session. Switching backends invalidates the entire
  test set and requires fakeredis or a real Redis in CI.
- **The actual problem is unbounded growth**, not query latency. A
  cleanup worker fixes the actual problem with ~70 lines of code and zero
  risk to the auth surface.

## Retention rationale

`RETENTION_HOURS = 24` against rate-limit windows of 15 minutes
(`_AUTH_RATE_WINDOW_MINUTES`, `_USERNAME_LOCKOUT_WINDOW_MINUTES` in
`app/api/v1/auth.py`). The 96x buffer ensures:

- A check evaluating its 15-minute window can never race a deletion that
  removes a row still inside that window.
- If we ever extend the windows (e.g. to 1h), we don't need to
  simultaneously bump retention.
- A `test_retention_exceeds_auth_windows` regression test in
  `tests/workers/test_auth_rate_limit_cleanup_worker.py` fails loudly if
  someone shrinks the buffer.

## Revisit when

- `auth_rate_limits` exceeds ~10M rows steady state (worker is failing
  silently or DB is genuinely hot enough that index scans show up in
  pg_stat_statements).
- We need cross-process or multi-replica rate limiting (current design
  assumes a single Postgres source of truth — Redis would help here, but
  so would partitioning the table).
- The lockout policy needs sub-minute granularity, where Redis sliding
  windows are markedly cleaner than SQL counts.
