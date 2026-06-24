# Level-3 Pattern — Standalone Deployable Service Blocks

How a **heavy, integration-bound block** is extracted as its own deployable
service rather than an in-process package.

This is the **Level-3** counterpart to `BACKEND_BLOCK_PATTERN.md` (Levels 1–2):
the in-process pattern produces a mountable package (`tribunal-<id>`) that
imports the host's `app.core_api` and shares the host's process, DB, and Alembic
chain. The Level-3 pattern produces a **separate FastAPI app + worker process**
that runs as its own Railway service and talks to the host CRM over
HTTP/WebSocket.

> **Scope.** This document defines a *pattern* plus reference scaffolding under
> `services/_template/`. It does not extract any block. Read each block's
> `docs/blocks/<id>/BLOCK.md` manifest first; the manifest's `status` field uses
> `service` for a block that runs as its own deployable (see `BLOCK_SCHEMA.md`),
> and the manifest's *How to Extract* section may explicitly recommend
> **"Level 3 (standalone service)"** (e.g. `voice/BLOCK.md`).

---

## 1. Levels at a glance

| Level | Shape | Shares host process? | Shares host DB? | Lifecycle |
|---|---|---|---|---|
| **1** Decoupled | still in `backend/app/`, sideways imports severed | yes | yes (shared) | host monolith |
| **2** Package | `tribunal-<id>` uv-workspace package, `get_router()` mounted | yes | yes (shared `Base.metadata`, shared Alembic chain) | host monolith |
| **3** Service | own FastAPI app + worker, own Railway service | **no** | **no** (by default) | independent deploy |

Level 1–2 blocks are *copy-paste / mountable libraries*: they ship as code the
host imports. A Level-3 block is a *running process* the host addresses over the
network. That is the fundamental difference every section below follows from.

## 2. When to choose Level 3

Promote a block to Level 3 when one or more of these hold (they come straight
from the Tier B manifests):

- **Hard real-time constraints.** Per-call WebSocket media streaming, in-process
  live-call registries, and voice-bridge concurrency caps cannot tolerate a
  co-located monolith's GC pauses or request-queue starvation. (`voice`)
- **A dedicated scaling / failure profile.** The block must scale or roll
  independently of the API (e.g. its own CPU/memory ceiling, its own replica
  count, its own crash-blast-radius). Voice wants sticky sessions and a tight
  connection budget; the CRM API does not.
- **Provider-bound webhook ownership.** The block is the natural terminus for an
  external provider's webhooks (Telnyx media events, Stripe checkout) and wants
  those endpoints on its own public URL, not the host's.
- **Stateful long-lived connections.** WebSockets / persistent provider sockets
  that must pin to one process.

Do **not** choose Level 3 for a block that is read-mostly, stateless, or only
runs as a scheduled poll — Levels 1–2 keep it simpler. The decision is recorded
per block (see §7).

## 3. The host ↔ service contract

A Level-3 service block exposes a fixed surface and abides by a fixed contract
with the host. The host never imports the service's code; it calls it over HTTP
(or WebSocket) using a **generated typed client** (§5). The service never reaches
into the host's DB (§4). Everything below is what makes that boundary safe.

```
                 ┌──────────────────────── host CRM (backend/) ─────────────────────────┐
                 │  FastAPI API  •  Postgres  •  Redis  •  ~27 workers (in-process)      │
                 │  app/core/security.py  app/core/encryption.py  app/core_api            │
                 └───────────────▲───────────────────────────────▲───────────────────────┘
                                 │ ① signed service token         │ ⑥ signed event callback
                                 │   (HS256 JWT, type=service)    │   (HMAC-SHA256 + ts)
          ② workspace-scoped      │                                │
             call (typed client)  │                                │
                                 ▼                                │
        ┌──────────────────────────── service: <block-id> ──────────────────────────────┐
        │  own FastAPI app  •  own worker process(es)  •  own Railway service             │
        │  /webhooks/<provider>   (③ external providers point HERE)                       │
        │  own /livez /readyz     (④ independent health)                                 │
        │  own openapi.json       (⑤ host generates a typed client from this)            │
        │  optional slice DB      (§4 — voice owns caller_memories; payments is stateless)│
        └────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Transport & topology

- The service is its own ASGI app (`uvicorn app.main:app`) behind its own Railway
  service with its own `PORT`, healthcheck (`/readyz`), and `startCommand` —
  mirroring `backend/railway.toml`. See the template's `railway.toml`.
- The host addresses the service at a base URL from config, e.g.
  `VOICE_SERVICE_URL`/`PAYMENTS_SERVICE_URL`, never a hardcoded host.
- Real-time channels (voice media, live supervision) use **WebSocket** routes
  mounted on the service, authenticated with a short-lived ticket minted by the
  host — the same `/auth/ws-ticket` JWT pattern the host already uses for its
  voice bridges (`docs/blocks/voice/BLOCK.md`).

### 3.2 Service-to-service auth — signed tokens

The host authenticates to the service with a **signed service-to-service
token**, reusing the host's existing JWT machinery verbatim in shape.

- **Sign with the host's `SECRET_KEY`** (the same `settings.secret_key` that
  signs user access/refresh tokens in `backend/app/core/security.py`), or a
  dedicated `SERVICE_TOKEN_SECRET` for a service-mesh boundary. Either is HS256
  (`settings.algorithm`, default `"HS256"`) — symmetric, so both sides share the
  secret as an env var; no key distribution problem.
- The token is a JWT with a **`type: "service"`** claim (mirroring the
  `type: "access"`/`type: "refresh"` discriminator in `security.py`), a short
  `exp` (minutes), an `aud` scoped to the service id (e.g. `"voice"`), and a
  `workspace_id` claim so the service can attribute the call to a tenant.
- **The service verifies** signature + expiry + `type`/`aud`, exactly as
  `decode_access_token` verifies `type == "access"` and rejects bad signatures
  via `jwt.InvalidTokenError`. Reject anything else with `403`.
- This is a *bearer* between two trusted backends over TLS; it is **not** user
  auth. The service trusts that the host has already authenticated the user and
  resolved `workspace_id`. Never forward a user's access token to the service —
  mint a fresh, short-lived service token per call.

The template ships a self-contained `app/security.py` implementing both the
verify path (service-side) and a documented mint path (host-side), copied from
the `security.py` pattern so the two stay structurally identical.

### 3.3 Per-workspace credential passing — the Fernet vault

Per-workspace third-party credentials live Fernet-encrypted in the host, on the
`workspace_integrations` table (`encrypted_credentials` column, encrypted with
`backend/app/core/encryption.py::encrypt_json`/`decrypt_json`, derived from
`ENCRYPTION_KEY`). Two ways to surface them to a service; **default to (a)**:

- **(a) Host decrypts, injects per call (default).** The host resolves the
  workspace's `WorkspaceIntegration` row, decrypts the credential dict in
  process, and passes the needed secret to the service **in the request body or
  a header on that single call** (over TLS). The service holds the secret only
  for the duration of the request and never persists it. This keeps `ENCRYPTION_KEY`
  on the host alone. Use this for any stateless / request-driven flow.
- **(b) Service owns its slice and shares `ENCRYPTION_KEY` (opt-in).** When the
  service must read per-workspace credentials **autonomously** — its own polling
  workers or its own inbound webhook handlers that the host is not in the call
  path for — give the service a narrow slice table that stores the same
  Fernet ciphertext and set the same `ENCRYPTION_KEY` in the service's env. The
  ciphertext round-trips unchanged because `_derive_fernet_key` is deterministic.
  The service decrypts only its own slice; it still never sees the host's other
  tables.

Never log a decrypted credential. The host's `openai_credentials.py` is the
reference for "bearer values are intentionally never logged."

### 3.4 Data ownership — call back vs. own a slice DB

**A service does not share the host's database by default.** It gets the data it
needs one of two ways:

- **Call back to the host's v1 API (default).** When the service needs
  contact/appointment/opportunity data, it calls the host's existing
  `/api/v1/...` endpoints with a service token, scoped to the `workspace_id`.
  The host stays the system of record. Use this for read-mostly, low-frequency,
  or fan-out-one-record access (fetch a contact's details, look up a campaign).
- **Own a narrow slice DB (opt-in, justified by latency).** When the service
  needs **low-latency, high-frequency, hot-path** access that cannot afford a
  network hop on every event — per-call caller-memory lookups during a live
  voice stream — the service owns a narrow slice (its own tables, its own
  migrations, its own Postgres or a schema in the shared Postgres instance). It
  keeps that slice eventually consistent with the host by subscribing to host
  events (§6).

**Decision criteria (apply per block):**

| Block | Data approach | Why |
|---|---|---|
| `voice` | **Own a slice** (`caller_memories`, live-call state) | Real-time media loop needs sub-hop caller-context reads; in-process `LiveCallRegistry` state is intrinsic to the service. |
| `payments` | **Stateless callbacks** — no own data store needed | Creates a Checkout Session and reconciles via Stripe webhook; the `call_payments` row can live on the host and be written back through an event. |
| `appointments` | **Call back** (contacts/availability) + own `appointments`/`bookable_staff` slice if extracted | Booking is a thin Cal.com pass-through; reminders are scheduled, not hot-path. |
| `messaging` | **Call back** for contacts/tags/segments; own campaign/conversation state if extracted | Outbound delivery is hot but contact resolution is read-only fan-out. |

Record the chosen approach in the block's `BLOCK.md` extraction section.

> **Shared Postgres instance is allowed.** A service may use the *same* Postgres
> server for its slice via a separate database (or schema) with its **own**
> connection pool and its **own** Alembic chain — it just must not open
> transactions against the host's tables. Cross-service foreign keys to the
> host's tables are forbidden; use a soft id reference (e.g. `contact_id: int`)
> resolved over the API.

### 3.5 Typed client the host uses to call the service

The service **exposes its own `/openapi.json`**. The host consumes it to produce
a **generated typed client**, mirroring exactly how the frontend consumes the
backend's OpenAPI:

- Frontend today: `openapi-typescript ../backend/openapi.json -o src/lib/api/_generated.ts`
  (see `frontend/package.json`), wrapped by the typed `apiClient` in
  `frontend/src/lib/api/_client.ts`.
- Host → service: the service's `openapi.json` is checked in, and the host
  generates a typed Python client against it. Prefer a typed `httpx`-based client
  (e.g. via `openapi-python-client` or a repo-local generator) so a schema change
  in the service surfaces as a **compile/type error on the host** before deploy.

The contract is: **service changes its API → regenerate its `openapi.json` → host
regenerates the client → commit both.** This is the Level-3 analogue of the
frontend `make codegen` drift check (`make ci.codegen`). The template's
`host_client/` ships the client stub and the regeneration note.

### 3.6 Webhook routing — providers point at the service

External providers (**Telnyx / Stripe / Cal.com / Resend**) route their webhooks
to the **service**, not the host, when the service owns that integration:

- The service mounts its own `/webhooks/<provider>` endpoints and runs the
  provider's signature verification **on the service**, reusing the host's
  verified patterns from `backend/app/core/webhook_security.py`:
  - Telnyx: ed25519 over `timestamp|payload` with a 5-minute replay window
    (`validate_telnyx_signature` / `verify_telnyx_webhook`).
  - Cal.com: HMAC-SHA256 over the raw body with a timestamp + 5-min replay window
    (`validate_calcom_signature` / `verify_calcom_webhook`).
  - Stripe: Stripe-Signature header verification (mirror the HMAC/timestamp shape).
- Both patterns include an explicit `skip_webhook_verification` dev-only bypass,
  gated on a setting — copy that flag into the service's config.

### 3.7 Events — service notifies the host

The service tells the host about outcomes (payment captured, call ended,
appointment booked) by **POSTing a signed event** to a host endpoint, e.g.
`POST /webhooks/service/<service-id>` on the host. The event is signed with an
**HMAC-SHA256** over `timestamp|body`, reusing the exact Cal.com-style scheme
from `webhook_security.py` (`signed_payload = f"{timestamp}|".encode() + body`),
and the host verifies it with the shared `SERVICE_TOKEN_SECRET`. Events must be
**idempotent** (keyed by an event id) so retries don't double-apply — reuse the
host's `derive_webhook_delivery_key` idempotency shape (exposed via
`app.core_api`) when the host processes them.

This is the service→host arrow; §3.2 is the host→service arrow.

## 4. Lifecycle, health & scaling

- **Independent deploy.** Each service has its own `railway.toml` (mirroring
  `backend/railway.toml`: nixpacks builder, `startCommand`, `healthcheckPath =
  /readyz`, `restartPolicyType = "on_failure"`). Deploy/rollback does not touch
  the host.
- **Independent health.** The service exposes `/livez` (process up) and `/readyz`
  (startup complete + its own deps reachable), mirroring the host's
  `backend/app/api/v1/health.py`. The orchestrator probes **the service's**
  `/readyz`, not the host's.
- **Own worker process.** A service that polls runs its own worker loop in a
  separate process (`uv run <service>-workers`), exactly as the host splits out
  `backend-workers` (`app.workers.runner:main`) when scaling API replicas
  (CLAUDE.md). A service's poll loop is **not** one of the host's ~27 in-process
  workers — it lives in the service.
- **Scaling blast radius.** N replicas of the host must not multiply the
  service's poll loops, and vice versa. Stateful services (voice) need sticky
  routing / single-leader coordination for in-process registries; stateless
  services (payments) scale horizontally with no coordination.

## 5. The template — `services/_template/`

A complete, bootable reference service lives at `services/_template/`:

```
services/_template/
  pyproject.toml        # own distribution + deps; own [project.scripts]
  railway.toml          # own Railway service (mirrors backend/railway.toml)
  Dockerfile            # multi-stage, uv-installed (mirrors backend/Dockerfile)
  README.md             # the service contract, env vars, run instructions
  .env.example          # every env var with a safe default/dev value
  app/
    __init__.py
    config.py           # pydantic-settings; boots with defaults for local dev
    security.py         # service-token verify + event sign/verify (from security.py / webhook_security.py)
    deps.py             # FastAPI deps: verify_service_token, current workspace
    router.py           # business endpoints (placeholder + how-to)
    worker.py           # standalone asyncio worker loop (own process)
    health.py           # /livez /readyz (mirrors backend health.py)
    main.py             # FastAPI app: lifespan starts worker, mounts router + health
  host_client/
    client.py           # typed httpx client the HOST uses to call THIS service
    README.md           # how the host regenerates the client from the service openapi.json
```

It is **fully self-contained**: no `import app.core_api`, no host DB, no host
process. It reuses the host's *patterns* (JWT verify, Fernet, HMAC webhook
signing) as its own implementations so the two stay structurally aligned.

## 6. Scaffolding a new service

```bash
python3 scripts/blocks/scaffold_service.py <block-id>
# e.g. python3 scripts/blocks/scaffold_service.py voice
```

This clones `services/_template/` → `services/<block-id>/`, substituting the id
into package/import names, titles, and config. It refuses to overwrite an
existing service and validates the id against `docs/blocks/registry.json`.

After scaffolding:

1. `cd services/<block-id> && uv sync` to install.
2. Fill `app/router.py` with the block's endpoints; wire provider webhooks under
   `/webhooks/<provider>` using `app/security.py`'s signature helpers.
3. Pick the data-ownership mode (§3.4): call-back to the host v1 API (default) or
   add a slice DB + its own Alembic chain.
4. Set `SERVICE_TOKEN_SECRET` (= host `SECRET_KEY` or the mesh secret) and the
   host base URL (`HOST_API_URL`) in the service env; symmetrically set
   `<BLOCK>_SERVICE_URL` in the host env.
5. Generate the host client from the service `openapi.json` and wire the host to
   call through it.
6. Point the external provider's webhook URL at the service's public URL.

## 7. Mapping to the Tier B blocks

| Block | Level-3 fit | Data (§3.4) | Webhooks (§3.6) | Notes |
|---|---|---|---|---|
| `voice` | **Yes — recommended** (`BLOCK.md` says so) | own slice (`caller_memories`, live-call state) | Telnyx voice/SMS media + events | Sticky routing; own concurrency caps; the hottest real-time path. |
| `payments` | Yes (lightweight) | stateless — write back via event | Stripe `checkout.session.completed` | Mostly a Checkout-session factory + idempotent reconciliation. |
| `appointments` | Maybe | call-back (contacts/availability) + optional own slice | Cal.com booking webhooks | Thin Cal.com pass-through; reminders are scheduled, not hot. |
| `messaging` | Maybe | call-back for contacts/tags; own campaign/conversation state if extracted | Telnyx SMS + mac-relay deliver/reply | Extract with `voice` — they share the telephony cycle. |

## Rules of thumb

- **Level 3 = a running process, not a library.** The host calls it over the
  network with a generated client; it never imports the service's code.
- **Auth is symmetric JWT, reused verbatim in shape.** Sign service tokens with
  the host's `SECRET_KEY` (HS256, `type=service`, `aud=<id>`, `workspace_id`),
  the same way `security.py` signs user tokens.
- **Credentials stay Fernet-encrypted; default to host-decrypts-and-injects.**
  Share `ENCRYPTION_KEY` only when the service must decrypt its own slice.
- **Default to calling back to the host v1 API.** Own a slice DB only for
  hot-path low-latency reads (voice), and never across the host's tables.
- **Providers point at the service; the service signs events back to the host.**
  Both reuse the verified `webhook_security.py` signature schemes.
- **Each service is independently deployable and independently healthy.** Own
  `railway.toml`, own `/readyz`, own worker process, own scaling profile.
