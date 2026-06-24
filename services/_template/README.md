# tribunal-service-__BLOCK_ID__

Standalone **Level-3 service** for the **__BLOCK_ID__** block. Its own FastAPI
app + worker process, deployed as its own Railway service, that the host CRM
talks to over HTTP using a generated typed client.

> Mirrors `docs/blocks/__BLOCK_ID__/BLOCK.md`. See
> [`docs/blocks/SERVICE_BLOCK_PATTERN.md`](../../docs/blocks/SERVICE_BLOCK_PATTERN.md)
> for the full host ↔ service contract.

## Run locally

```bash
uv sync
uv run uvicorn app.main:app --reload          # API + worker (in-process)
# or run the worker as its own process:
uv run __BLOCK_ID__-workers
```

- API: `http://localhost:8000/docs`
- Health: `GET /livez` (process up) · `GET /readyz` (startup complete)
- OpenAPI: `GET /openapi.json` (host generates a typed client from this)

## Host ↔ service contract (summary)

| Direction | Mechanism | Pattern reused |
|---|---|---|
| Host → service | `Authorization: Bearer <service-token>` (HS256 JWT, `type=service`, `aud=__BLOCK_ID__`, `workspace_id`) | `backend/app/core/security.py` |
| Service → host | `POST {HOST_API_URL}{HOST_EVENT_WEBHOOK_PATH}` with HMAC-SHA256 `timestamp|body` headers | `backend/app/core/webhook_security.py` |
| Provider → service | external webhooks under `/webhooks/<provider>` with provider signature verification | `backend/app/core/webhook_security.py` |

See `app/security.py` for the implementation and `host_client/` for the host-side
caller.

## Data ownership

Default: **call back to the host v1 API** (`HOST_API_URL`) for any data this
service does not own. Own a narrow slice DB only for hot-path low-latency reads
(see `SERVICE_BLOCK_PATTERN.md` §3.4). Add `sqlalchemy`/`asyncpg`/`alembic` to
`pyproject.toml` and a `DATABASE_URL` when the service owns a slice.

## Environment variables

| Var | Required | Purpose |
|---|---|---|
| `SERVICE_TOKEN_SECRET` | **prod** | HS256 secret shared with the host (use the host's `SECRET_KEY`) |
| `HOST_API_URL` | yes | Base URL of the host CRM's v1 API + event receiver |
| `HOST_EVENT_WEBHOOK_PATH` | yes | Path the host receives signed events on |
| `ENCRYPTION_KEY` | slice only | Host's Fernet key (only if the service decrypts per-workspace creds) |
| `DATABASE_URL` | slice only | The service's own Postgres slice |
| `SKIP_WEBHOOK_VERIFICATION` | dev | Bypass provider signature checks locally |
| `RUN_WORKER` / `WORKER_POLL_INTERVAL_SECONDS` | no | Worker lifecycle |

Full list with defaults: `app/config.py`.

## Deploy

Each service is its own Railway service using `railway.toml` (healthcheck
`/readyz`). It deploys/rolls back independently of the host CRM.
