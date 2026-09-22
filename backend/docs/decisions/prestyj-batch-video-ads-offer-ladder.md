# Prestyj Batch Video Ads offer ladder representation

## Decision

Represent Batch Video Ads as one `offers` row with structured metadata, not four linked offer rows.

The product has one fulfillment path, one public slug, one checkout flow, and one autonomous negotiation motion. The 100, 300, 500, and 1,000 ad packs are selectable package options within that product, so splitting them into four offers would duplicate terms, landing-page data, and sales-agent strategy.

## Storage

The canonical ladder definition lives in `backend/app/services/offers/prestyj_batch_video_ads.py`. The seed harness imports that module and writes the same data onto the `Offer` row:

- `package_options`: queryable JSONB array of pack facts (`ad_count`, `price`, `problems_covered`, `cost_per_ad`, role, and source URL).
- `negotiation_sequence`: ordered JSONB array for anchor → fallback → upsell → close behavior.
- `strategy_metadata`: JSONB object for source URL, default anchor/fallback/upsell keys, autonomy notes, scope exclusions, and human-escalation triggers.

The legacy `value_stack_items`, `offer_price`, `regular_price`, and terms remain populated for existing public-offer UI and campaign compatibility, but new sales-agent behavior should read the structured fields above.

## Sales motion

The 500-ad pack is the anchor and sweet spot. If the buyer resists budget or volume, the agent falls back to the 100-ad sampler. If the buyer wants broader testing or speed to find winners, the agent upsells to the 1,000-ad scale pack. Human escalation is only for add-ons beyond the batch offer, such as running ads, installing AI agents, or consulting.
