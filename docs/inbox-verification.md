# Inbox verification

How to check the waiting inbox (Today → waiting → reply → next) locally. Everything here uses synthetic data, never touches the application database, and cannot send real messages.

## 1. Disposable PostgreSQL

The integration suite and the fixture server only accept a loopback database named `tribunal_inbox_test`. Anything else is refused.

```bash
docker run -d --rm --name tribunal-inbox-verification \
  -e POSTGRES_USER=tribunal_inbox_test -e POSTGRES_DB=tribunal_inbox_test \
  -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:55432:5432 postgres:17-alpine
```

To use another port, set `INBOX_TEST_DATABASE_URL`, for example `postgresql+asyncpg://tribunal_inbox_test@127.0.0.1:55433/tribunal_inbox_test`.

## 2. Service and API tests (real SQL)

```bash
cd backend
SECRET_KEY=<any-32+-char-test-value> ENCRYPTION_KEY=<fresh Fernet key> \
  uv run pytest -m integration tests/integration/test_inbox_postgres.py -q
```

Covers the shared "needs a human reply" rule, searching past row 100, counts, sort and page limits, lookup of a selected thread, reads that change nothing, the conditional read race, and cross-workspace denial. Each test builds and drops its own schema.

## 3. Real HTTP checks through the eyes probe

The fixture server rejects all writes except read acknowledgments and the read-only search route. It starts no workers and has delivery disabled.

```bash
cd backend
KEY=$(uv run python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
SECRET_KEY=<test-value> ENCRYPTION_KEY=$KEY RUN_BACKGROUND_WORKERS=false \
  uv run uvicorn tests.integration.inbox_fixture_server:app --host 127.0.0.1 --port 8001 --no-access-log
# second shell, same SECRET_KEY and ENCRYPTION_KEY
uv run python -m tests.integration.inbox_http_check
```

The server keeps its seeded rows between runs. Use the **same** `ENCRYPTION_KEY` each time, or start from a fresh container. A different key causes `InvalidToken` 500s when stored encrypted fields are read.

The check refuses to run unless `/readyz` reports `fixture: true` and `delivery_disabled: true`. It writes `.ezcoder/eyes/out/inbox-http-verification.json`.

## 4. Browser flow

```bash
cd frontend && npx playwright test e2e/inbox-reliability.spec.ts
```

All API calls are intercepted with synthetic data (122 conversations). No credentials, providers or backend needed.

## Last observed results (25 September 2026)

| Check | Result |
| --- | --- |
| `test_inbox_postgres.py` | 7 passed |
| `test_today_queue_service.py` (with `make dev.db` running) | passed as part of the full backend suite |
| HTTP probe | 9/9 expected statuses: GET/POST list 200, detail/messages/read 200, page_size=101 → 422, unknown thread → 404, other workspace → 404, no token → 401 |
| Playwright `inbox-reliability.spec.ts` | 5 passed (desktop, 320px, keyboard, recovery, >100 search) |
| Frontend lint / typecheck / Vitest / build | 0 errors / clean / 498 passed / built |
| `make codegen` | regenerated; POST search route now in the generated client |

Local timings on the same 100+ row synthetic dataset (11 requests each, warm median): legacy list page of 100 ≈ 97 ms / 42 KB; legacy page of 50 ≈ 98 ms / 21 KB; new inbox page of 50 ≈ 97 ms / 25 KB. **Speed is unchanged.** The gains are that the list is complete (search and counts cover every page) and the payload is about 40% smaller than the old 100-row fetch. This is not a production latency measurement.

## Known unrelated failures

Before this change, `make ci.backend` / `make ci.frontend` already stopped at `ci.env`, because five AI model settings (`CALLER_MEMORY_MODEL`, `PROMPT_IMPROVEMENT_MODEL`, `REPORTS_MODEL`, `TRANSCRIPT_ANALYSIS_MODEL`, `TRANSCRIPT_JUDGMENT_MODEL`) are missing from `backend/.env.example`. `blocks.lint.backend` also flags `reminder_worker → payments.booking_deposit`. The full backend suite has 17 failures and 7 errors, and they reproduce identically on commit `0ed1293` without these changes: campaigns, realtime token, outbound missions, nudge delivery, env drift, idempotency keys and Resend contracts.
