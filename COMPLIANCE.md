# Compliance register

Snapshot: 2026-09-24 · Base commit: `33ea370` · Engineering guidance, NOT LEGAL ADVICE.

## Scope and exposure

This is an inline register for vertical sales/proof exports only, not a product-wide compliance audit. Confirmed from code: real-estate, roofing and HVAC scripts support AI voice/SMS follow-up; the exporter creates inactive drafts and does not send, persist or publish. Assumed: US operators using documented inbound permission. Other jurisdictions require separate review before activation.

| ID | Severity | Trigger | Evidence | Obligation / status | Guard |
| --- | --- | --- | --- | --- | --- |
| VP-01 | HIGH | Performance claims without substantiation | RUNTIME: synthetic case-study tests | Exports explicitly remain internal drafts; $224/$487 is unverified brief context, never customer proof | Publication flags remain false; synthetic fixture explicitly labelled |
| VP-02 | LAWYER | Voice/SMS consent, recording and local advertising | CODE: shared rules and vertical addenda | Operator/counsel approval required before use; catalog rules do not enforce sending consent | Inactive offers and lead magnets; review gates travel with exports |
| VP-03 | LAWYER | Fair housing, representation, contractor and emergency claims | CODE: vertical scripts and objection libraries | Broker/contractor approval required; no valuation, diagnosis, coverage or availability guarantees | Vertical addenda included in response playbooks and sales proof |

## Implemented in this pass

- Aggregate-only case-study input shape; no contact/transcript fields; unknown fields rejected.
- CLI validation failures do not echo private input values. Free-text fields still require operator redaction.
- Shared operating rules and evidence checklists accompany exported lead magnets.

## Open / needs a lawyer

Approve local consent, recording, licensing, fair-housing and advertising requirements before campaign activation. Verify benchmark provenance and customer publication rights before sales use. No numeric claim is substantiated by this code or its synthetic test fixture.

## Not checked / re-verify before relying

No legal effective dates are asserted. No live send, production data, website, payment flow or jurisdiction-wide review was performed here. Existing runtime sending controls are unchanged. Reconcile real cohorts, costs and permission records separately; evidence references are not fetched or authenticated by the exporter.
