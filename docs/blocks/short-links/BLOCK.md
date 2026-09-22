---
id: short-links
name: Short Links & Click Tracking
tier: A
status: extracted
summary: Generates tracked short URLs for outbound SMS and records per-click events (count, last-clicked, IP/UA/referer), attributing clicks back to contacts and campaigns.
owns_paths:
  - backend/packages/short-links/
public_api:
  - backend/packages/short-links/src/tribunal_short_links/__init__.py::get_router
  - backend/packages/short-links/src/tribunal_short_links/__init__.py::shorten_urls_in_text
  - backend/packages/short-links/src/tribunal_short_links/service.py::record_click
  - backend/packages/short-links/src/tribunal_short_links/models.py::ShortLink
  - backend/packages/short-links/src/tribunal_short_links/models.py::LinkClick
depends_on: [core]
external_integrations: []
env_vars:
  - PUBLIC_BASE_URL
db_tables:
  - backend/packages/short-links/src/tribunal_short_links/models.py::short_links
  - backend/packages/short-links/src/tribunal_short_links/models.py::link_clicks
alembic_migrations: shared chain — a9b0c1d2e3f5 (sms_link_tracking)
workers: []
extraction_effort: low
extraction_notes: The data models depend only on core (app.db.base.Base), but the click generator that creates ShortLink rows (shorten_urls_in_text) currently lives in the messaging block and is invoked from the voice block's Telnyx SMS sender, so the write path — not the models — is the real coupling to relocate.
---

## Overview

Short links make outbound SMS measurable. When a message is sent, any `http(s)` URL in the body is replaced with a tracked `/r/{short_code}` link (a 7-char base62 code, unique-indexed). A `ShortLink` row stores the target plus optional `contact_id`, `campaign_id`, and `message_id` for attribution. The public redirect router resolves the code, writes a `LinkClick` event (clicked-at, IP, user-agent, referer), increments `click_count`/`last_clicked_at` and the owning campaign's `links_clicked`, then 302s to the target. This is the most standalone backend block by ownership: two tiny models plus one public router, depending only on `core`.

## Internal Dependencies

The two models import only core:

- `backend/app/models/short_link.py:10: from app.db.base import Base` → **core**.
- `backend/app/models/link_click.py:10: from app.db.base import Base` → **core**.

Beyond the owned models, the *write path* is wired through other blocks (no import lands inside this block, so the inventory shows `depends_on: [core]` only — but these must be relocated to keep tracking working):

- `backend/app/services/messaging/link_shortener.py` (block: **messaging**) — `shorten_urls_in_text(...)` creates `ShortLink` rows. It imports `app.models.short_link.ShortLink` (a sideways read *into* this block from messaging).
- `backend/app/services/telephony/telnyx.py:28: from app.services.messaging.link_shortener import shorten_urls_in_text` (block: **voice** → **messaging**) — the Telnyx SMS sender calls the shortener before dispatch.
- The redirect router (`app/api/redirects.py`) imports the shared `app.models.campaign.Campaign` to bump `links_clicked`, and uses core's `app.db.session.get_db`.

## Public Surface

- Route: `GET /r/{short_code}` (mounted at the app root in `app/main.py`, **no `/api/v1` prefix** — these are user-facing SMS URLs) → logs a click and 302-redirects.
- Models: `ShortLink` (workspace-scoped, unique `short_code`, FKs to contacts/campaigns/messages) and `LinkClick` (per-click event, FK to `short_links`).
- Helper consumed by senders: `shorten_urls_in_text(...)` — now the block's public write API (`tribunal_short_links.shorten_urls_in_text`, alias `shorten_url`).

## Status: extracted

This block is packaged into a mountable workspace member. The block source no
longer lives in the app tree (`backend/app/api/redirects.py` and
`backend/app/services/messaging/link_shortener.py` were removed); it moved to
**`backend/packages/short-links/`** (uv distribution `tribunal-short-links`,
importable as `tribunal_short_links`).

The write-path coupling is severed: the Telnyx SMS sender
(`app/services/telephony/telnyx.py`) now calls the block's public API
`from tribunal_short_links import shorten_urls_in_text` instead of reaching into
the messaging block's `link_shortener`. The redirect router's click-recording
logic was extracted into `tribunal_short_links.service.record_click`.

The two ORM models live in `tribunal_short_links.models`; thin back-compat shims
remain at `app/models/short_link.py` and `app/models/link_click.py` that
re-export `ShortLink`/`LinkClick`, so existing `from app.models...` imports keep
working and `app.db.model_registry` still discovers the tables for Alembic.

### Install & mount (backend)

1. The package is a uv workspace member (`backend/packages/short-links/`); the
   host `backend/pyproject.toml` declares `tribunal-short-links` as a workspace
   dependency (`[tool.uv.sources]`). `uv sync` from `backend/` links it editable.
2. Mount the redirect router at the **app root** (already wired in
   `app/main.py`), preserving the public `/r/{short_code}` URL exactly:
   ```python
   from tribunal_short_links import get_router as get_short_links_router
   app.include_router(get_short_links_router())   # -> GET /r/{short_code}
   ```
   `get_router()` returns an unprefixed `APIRouter` (these are user-facing SMS
   URLs, so **no** `/api/v1` prefix).
3. SMS/voice senders rewrite outbound URLs through the block's write API:
   ```python
   from tribunal_short_links import shorten_urls_in_text
   body = await shorten_urls_in_text(body, workspace_id=..., db=..., base_url=settings.public_base_url, ...)
   ```
4. Provide the declared `env_vars` (`PUBLIC_BASE_URL`, read by senders to build
   `/r/{code}` URLs). The block owns the `short_links` + `link_clicks` tables,
   but their creating revision (`a9b0c1d2e3f5`) stays in the host's shared
   Alembic chain, so there are no block-local migrations to wire.

## How to Extract

> Historical guide (the extraction has been performed — see *Status: extracted*).

1. Pull `core` only (models need just `app.db.base.Base`).
2. Copy `app/models/short_link.py`, `app/models/link_click.py`, and `app/api/redirects.py`.
3. Relocate the write path: move `link_shortener.py`'s `shorten_urls_in_text` into this block (it becomes the block's public write API) and have SMS senders call it via an injected hook instead of a direct import from `messaging`.
4. Decide attribution scope: the `contact_id`/`campaign_id`/`message_id` FKs and the redirect router's `Campaign.links_clicked` bump reach into contacts/messaging — either carry those tables or make the FKs nullable/optional in the new project.
5. Mount the redirect router at root; set `PUBLIC_BASE_URL` (used to build `/r/{code}` URLs).
6. Port `short_links` + `link_clicks` tables (migration a9b0c1d2e3f5).

## Risks

- **Write path lives elsewhere:** copying only the models yields a read-only redirector — without relocating `shorten_urls_in_text` no short links are ever created.
- **Cross-block FKs:** `short_links.campaign_id`/`contact_id`/`message_id` and the campaign click-count bump assume the messaging/contacts tables exist; standalone extraction must null these or bring the referenced tables.
- **Public, unauthenticated redirect:** `/r/{short_code}` is open by design; `target_url` is stored verbatim, so validate/allow-list targets to avoid open-redirect abuse if the creation path is exposed.
- **Workspace scoping:** `ShortLink` carries `workspace_id` but the redirect path resolves purely by `short_code`; keep codes unguessable (the 7-char base62 default) since the redirect is unscoped.
