# tribunal-reviews

Extracted package for the **reviews** block (Reviews & Reputation engine).

> Mirrors `docs/blocks/reviews/BLOCK.md`.

Reviews turns completed appointments into reputation: it requests SMS reviews
after jobs, runs the public rating gate (high raters → Google/Facebook, low
raters → private feedback firewall), tracks per-workspace reputation + sender
warming, and drafts on-brand AI replies.

## Mount

```python
from fastapi import FastAPI
from tribunal_reviews import get_router, get_public_router, register_workers

app = FastAPI()
app.include_router(get_router())          # /workspaces/{workspace_id}/reviews
app.include_router(get_public_router())   # /p/reviews  (no auth, rating gate)
```

The prefixes + tags are baked into the routers, so the host mounts them
prefix-free. Also: import `tribunal_reviews.models` so its tables register in
`Base.metadata` (the host does this via the back-compat shims in
`app.models.review` / `app.models.review_request`).

## Contract

| Export | Required | Purpose |
|---|---|---|
| `get_router() -> APIRouter` | yes | authenticated operator/settings/dashboard surface |
| `get_public_router() -> APIRouter` | yes | no-auth rating-gate landing page (`/p/reviews`) |
| `register_workers(registry)` | optional | hook `review_request_worker` + `reputation_worker` into host startup |
| `ReviewService` | — | public service API for sibling blocks (appointment completion, dashboard, webhooks) |
| `tribunal_reviews.models` | tables only | `Review` / `ReviewRequest` on the shared `Base` |

`review_request_registry` / `reputation_registry` are also exported for hosts
that wire a static worker spec list (as this repo's `app/workers/__init__.py`
does today).

## Migrations

The block owns the `reviews` + `review_requests` tables, created by revision
`7015928a0882` in the host's **shared** Alembic chain
(`backend/alembic/versions/`). This package therefore ships no `migrations/`
directory.

## Dependencies (cross-block public APIs)

Beyond `app.core_api` (settings, DB session, auth/workspace deps, pagination,
idempotency, automation bus, worker base), the block calls these sibling blocks
through their public APIs only:

- **voice** — `TelnyxSMSService` (send the review-request SMS).
- **appointments** — `resolve_from_number` (outbound from-number).
- **compliance** — `OptOutManager` (opt-out enforcement), `ReputationTracker` +
  `WarmingScheduler` (the reputation worker).
- **agent-brain** — `get_openai_bearer_token` (AI reply drafter credentials).
- **automations** — `emit_automation_event` (review/rating events), via
  `app.core_api`.

## Environment variables

No block-specific env vars. The block reads shared core settings via
`app.core_api.settings`: `TELNYX_API_KEY` (SMS send) and `FRONTEND_URL` (the
public landing-page link). OpenAI credentials are resolved by the agent-brain
block.

## Core contract

Imports core primitives **only** through `app.core_api` (settings, DB session,
auth/workspace deps, pagination, idempotency, worker base, automation bus). No
deep `app.core.*` / `app.db.*` / `app.api.deps` imports, no `os.environ`, no
hardcoded secrets.
