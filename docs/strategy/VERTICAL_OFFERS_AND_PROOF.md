# Vertical offers and evidence-gated sales kit

Status: **operator-ready drafts, not approved outbound campaigns or published customer case studies**. Based on the real-estate primary vertical and roofing/HVAC local-service niches in `BREAKTHROUGH_STRATEGY_REPORT.md` (week 1) and `STRATEGY_QUICK_REFERENCE.md`. The three reusable kits live in `backend/app/services/offers/vertical_kits.py`. `get_vertical_campaign_copy(key)` returns campaign-compatible `name`, `initial_message` and `follow_up_message` fields; copy them only after operator approval and add the actual sender/business identity. `{first_name}` is supported by `render_campaign_message`. Voice scripts and objections are agent briefing material, not automatically dispatched. Use documented inbound permission, and approve local calling, recording, SMS and professional-advertising rules first.

| Kit key | Buyer-facing offer | Qualified meeting / proof to collect | Objection angle |
| --- | --- | --- | --- |
| `real_estate` | Follow up with property inquirers, qualify buyer/seller intent, book agent conversations | Intent, area, timeline, agent availability; source-to-meeting funnel, permissioned redacted transcript, attendance | Browsing, already represented, valuation uncertainty |
| `roofing` | Follow up on estimate requests, qualify location/job type, schedule inspections | Property and decision-maker, service area, inspection slot; lead-to-inspection funnel, permissioned work example, attendance | Quote without inspection, insurance promise, urgent damage |
| `hvac` | Follow up on service requests, capture symptoms, schedule technicians | Service address, symptoms, technician slot; request-to-visit funnel, permissioned follow-up example, attendance | Remote diagnosis, same-day promise, gas emergency |

Every kit includes an opening voice script, two campaign-compatible SMS messages, objection/reply library, proof-asset checklist and a vertical compliance addendum. Shared operator rules in code call for identity/AI disclosure, opt-out handling and review; the catalog does not enforce consent or sending controls. These are not claims of legal compliance. Do not reuse the strategy report's hypothetical appointment, revenue, free-trial, scarcity or guarantee copy as historical results or approved terms.

## Proof pack: convert the work from tasks 01–12 into measured stories

The repository contains funnel instrumentation (`backend/app/services/campaigns/attempt_funnel.py`) with call attempts, connections, qualifications, bookings, completed appointments and **estimated AI call cost**. It does **not** contain an authenticated before/after result set for tasks 01–12 or a documented source for the supplied $224 hybrid / $487 human-only figures. No lift or customer outcome is asserted here. `build_proof_pack` in `backend/app/services/offers/roi_proof.py` computes rates and percentage-point changes from two dated, non-overlapping source exports; `publishable` stays false pending human review. A qualified call is **not** automatically a qualified meeting: count only booked meetings that also meet the documented qualification checklist. A completed appointment is the available show proxy; reconcile cancellations, no-shows and offline visits with the customer before publication.

For each customer story, export comparable windows (same vertical, market, lead source and attribution rules where possible), save the export identifiers, and record sample sizes. Fill in a one-pager only with permission and reconciled data:

> **[Customer / anonymous with permission] — [vertical, market, dates]**
> - Problem: [documented response / connect / attendance bottleneck].
> - Intervention: [specific shipped changes from tasks 01–12 and deployment dates; distinguish AI, human, and other changes].
> - Before: [attempts], [connected], [qualified], [booked], [qualified meetings], [shown], [all-in cost].
> - After: [same fields and definitions].
> - Outcome: [connect-rate percentage-point change], [booking-rate change], [show-rate change], [cost per qualified meeting].
> - Evidence: [dated source export IDs], [customer sign-off], [permission for any quote or image].
> - Limits: [cohort mix, seasonality, lead spend and human labor inclusion, incomplete attribution, sample size].

Build three stories once real exports exist: (1) real-estate lead response and connection, (2) roofing/HVAC booking and attendance, (3) cross-vertical qualified-meeting unit economics. Do not call roadmap targets or a feature shipped in tasks 01–12 an observed lift. The present case studies are **templates**, not customer testimonials.

### Sales proof card — hold pending substantiation

- **Claim to investigate, not publish:** “Hybrid $224 vs human-only $487 per qualified meeting.” These numbers were supplied in the task brief; there is no denominator, time window, sample, cost inclusion or independent benchmark source in this repository. If both figures prove comparable, the arithmetic difference is $263, or ~54% lower relative to $487. This is **not** a verified outcome or general market benchmark.
- Definition: qualified meeting = a booked meeting satisfying the same pre-agreed checklist in both groups. Keep *shown meetings* separate. Include lead acquisition, AI/provider fees, staff time, software and overhead consistently; distinguish paid/organic leads.
- Required proof: source and dates for each group, numerator and denominator, qualification review, cost ledger, cohort matching, geography/vertical, paid channel mix, exclusions and customer permission. If missing, leave the comparison out of sales copy.
- Suggested cautious pitch **after verification**: “In [customer/cohort] over [period], documented all-in cost per qualified meeting was $[hybrid] for [n] meetings versus $[human] for [n] under [same definitions]. Results vary; [methodology/link].” No universal savings claim.
- Do not use the `attempt_funnel`'s `estimated_cost_per_booked_usd` as all-in meeting cost. It multiplies calls by a configured AI cost estimate and omits acquisition and staff costs.

**Review gate:** Sales owner checks source exports and customer permission; operations checks qualified-meeting definitions and attribution; counsel reviews messaging consent, recordings, fair-housing/contractor claims and any published guarantee. Until then the catalog is internal enablement material, not a launch-ready campaign.
