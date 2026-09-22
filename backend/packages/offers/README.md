# tribunal-offers

Extracted package for the **offers** block (Offers & Offer Builder).

> Mirrors `docs/blocks/offers/BLOCK.md`.

Offers packages a workspace's value proposition into a publishable offer: a
multi-step builder (basics, value stack, pricing, guarantee, urgency, attached
lead magnets, review, publish) backed by `Offer` and the `OfferLeadMagnet` join.
AI can draft offer copy (agent-brain). Published offers render at public
`/p/offers/[slug]` pages where visitors opt in — creating a `Contact` and
delivering each attached lead magnet via the lead-capture delivery service. The
`prestyj_batch_video_ads` module is a static productized-offer pack definition
used for guided pricing/strategy.

## Mount

```python
from fastapi import FastAPI
from tribunal_offers import get_router, get_public_router

app = FastAPI()
app.include_router(get_router())          # /workspaces/{workspace_id}/offers
app.include_router(get_public_router())   # /p/offers  (no auth, public opt-in)
```

The prefixes + tags are baked into the routers, so the host mounts them
prefix-free. Also: import `tribunal_offers.models` so its tables register in
`Base.metadata` (the host does this via the back-compat shims in
`app.models.offer` / `app.models.offer_lead_magnet`).

## Contract

| Export | Required | Purpose |
|---|---|---|
| `get_router() -> APIRouter` | yes | authenticated offer authoring surface (`/workspaces/{workspace_id}/offers`) |
| `get_public_router() -> APIRouter` | yes | no-auth public offer opt-in pages (`/p/offers`) |
| `format_pack_terms` | — | prestyj productized-offer pack pricing helper (re-exported via `app.services.offers.prestyj_batch_video_ads` shim) |
| `tribunal_offers.models` | tables only | `Offer` / `OfferLeadMagnet` on the shared `Base` |

This block owns no background workers, so it exposes no `register_workers`.

## Dependencies

* **core** — DI/auth/session/scoping via `app.core_api`; `get_or_404` from
  `app.api.crud`.
* **lead-capture** — `deliver_lead_magnet_to_lead`, `LeadMagnet`,
  `LeadMagnetLead`, `LeadMagnetResponse` (public API of `tribunal-lead-capture`).
* **agent-brain** — `generate_offer_content` (`app.services.ai.offer_generator`).
* **contacts** — the shared `Contact` model (`app.models.contact`).

## Environment variables

None. The block reads no environment variables directly.

## Public URLs (do not change)

* `GET  /api/v1/p/offers/{slug}` — public offer landing data.
* `POST /api/v1/p/offers/{slug}/opt-in` — public opt-in (creates Contact +
  delivers attached lead magnets).

These exact paths are embedded in the frontend `app/p/offers/[slug]` pages and
the embedded `publicOffersApi` client.
