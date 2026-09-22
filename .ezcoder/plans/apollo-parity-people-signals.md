# Apollo Parity — Web Contact Scraping + Buying Signals

## Goal

Give The Tribunal an Apollo.io-style prospecting surface: search the web for
**people** (named individuals with titles at companies), attach **buying
signals** (already-running ads, ad/analytics tech installed, hiring, etc.),
reveal/verify contact emails, and push selected people into the existing
outbound rails — all workspace-scoped.

## What already exists (reuse, do not rebuild)

The codebase is already ~80% of the way there. Confirmed by reading source:

- **Source-agnostic discovery pipeline**: `LeadDiscoveryProvider` protocol +
  `RawLead`/`ProviderResult` value types (`backend/app/services/lead_discovery/`),
  dedupe helpers, `GooglePlacesLeadProvider`. Discovery jobs are persisted as
  `LeadDiscoveryJob` (`backend/app/models/lead_discovery_job.py`) with a
  `DiscoverySourceType` enum (already lists `web_scrape`, `linkedin`).
- **Prospect store**: `LeadProspect` (`backend/app/models/lead_prospect.py`)
  already supports partial identity (phone/email/website/owner-name), person
  fields (`first_name/last_name/full_name/title`), encrypted PII + lookup
  hashes, `evidence`/`provenance`/`signals` JSONB, `lead_score`, dedupe key,
  and promotion to `Contact` via `contact_id`.
- **Enrichment**: `ProspectEnrichmentWorker`
  (`backend/app/workers/prospect_enrichment_worker.py`) traces website
  email/phone/socials (`ContactTracer`), enriches business intel, and calls a
  config-gated Hunter/Apollo `email_finder`.
- **"Already running ads" signal — fully built**: `ad_intelligence/signals.py`
  (continuity, longest-running, refresh-rate, opportunity score, representative
  creative), Meta Ad Library + Google Ads Transparency providers, ICP
  thresholds (`icp.py`), advertiser→prospect promotion (`prospecting.py`),
  monitors, and the `/ad-library` API + frontend (`find-leads/ad-library`).
- **Outbound rails**: missions, prospect selection/suppression, sequences,
  enrollment — `outbound_missions` API + `outbound/` services.
- **Web scraping primitive**: `WebsiteScraperService` already fetches HTML,
  extracts social links, meta, and **ad/analytics pixels**
  (`_detect_ad_pixels`: meta_pixel, google_ads, ga, gtm, linkedin/tiktok).
- **Worker wiring**: `WorkerSpec` registry in `backend/app/workers/__init__.py`
  with per-worker `enabled_setting` flags; `BaseWorker` + `WorkerRegistry`
  pattern; all workers run in-process via `start_all_workers()`.

## The gap (what "Apollo parity" actually requires here)

1. **People, not just businesses/advertisers.** Today we discover a company or
   an advertiser and trace *one* public contact. Apollo's core is *named
   individuals* with title/seniority/department at a company. Need a
   people-extraction discovery source.
2. **A signals layer beyond ads.** "Running ads" exists but is siloed in
   `ad_intelligence`. Need a normalized, queryable signal model + a pluggable
   aggregator so a prospect can carry multiple signals (ads, installed ad-tech,
   hiring, …) and the search UI can filter on them.
3. **Email reveal + verification.** Pattern inference (`{first}@domain`) +
   deliverability verification (MX/SMTP or provider), gated and audited.
4. **An Apollo-style search UI + API**: filter people by title/seniority/
   location/industry/has-email/signal, reveal, and bulk add to a mission.

## Hard constraints / honesty (must be surfaced, not hidden)

- **Do not scrape LinkedIn or gated networks.** It violates their ToS and is
  legally risky. People extraction in v1 targets **first-party company web
  pages** (team/about/staff/contact pages reachable from the company domain),
  which is what `WebsiteScraperService` already does, plus optionally a licensed
  B2B data provider behind the existing provider protocol.
- **Two interchangeable people sources**, both behind `LeadDiscoveryProvider`:
  - (a) **Web crawl** (`web_people`) — the "scrape the web" path the user asked
    for. Compliant first-party crawl + LLM extraction + email pattern inference.
  - (b) **Licensed data API** (`people_db`) — config-gated adapter (Apollo/PDL
    shape; the repo already speaks Apollo's `/people/match`). True coverage
    parity needs a paid source; this keeps that pluggable without blocking v1.
- **Email/SMTP verification** can be slow and can get egress IPs blocked. Make
  it config-gated, off by default in dev, MX-only fallback when SMTP probing is
  disabled. No paid signup is required for v1 (pattern + MX); SMTP/provider is
  opt-in.
- Respect `robots.txt`/ToS via the existing scraper; add a per-domain crawl cap
  and reuse `scraping_limiter` rate limiting.

## Architecture decisions

- **New normalized signal model** `prospect_signals` (queryable) instead of only
  the freeform `LeadProspect.signals` JSONB, so the search API can filter/sort
  by signal type + strength in SQL. Keep writing the rich blob to
  `LeadProspect.evidence` for outreach copy (unchanged).
- **New signals package** `backend/app/services/signals/` with a `SignalProvider`
  protocol and an aggregator. First providers: `AdsSignalProvider` (wraps the
  existing `ad_intelligence` advertiser/opportunity data) and
  `AdTechSignalProvider` (from `WebsiteScraperService._detect_ad_pixels`).
  `HiringSignalProvider` + `FundingSignalProvider` are added as config-gated
  stubs with a clean seam (no fabricated data when unconfigured).
- **People extraction** as a new discovery provider so it reuses dedupe →
  prospect persistence → enrichment → promotion → outbound with zero changes to
  those layers. A `web_people` provider takes a company domain (or a query →
  company list via existing Google Places) and emits one `RawLead` per person.
- **Email reveal**: a pure `email_patterns` module (generate candidates) + a
  config-gated `email_verifier` (MX always; SMTP/provider opt-in). Wire into the
  existing `ProspectEnrichmentWorker._maybe_find_email` path.
- **Search API** as a new workspace-scoped router `prospects` (cross-mission
  people search), plus a saved-search row reusing the monitor pattern.
- **Frontend**: new `/find-leads/people` page following the existing
  `find-leads/ad-library` client patterns, query-keys, and `page-state`.

## Risks / things to verify during build

- `LeadProspect.dedupe_key` is per-workspace unique and currently company/owner
  oriented; person rows need a person-level dedupe facet (email-or
  name+domain). Add `dedupe_key_for_person` without breaking existing keys.
- People extraction quality from arbitrary HTML is noisy — must gate on
  confidence and never emit a prospect from a guessed email without marking it
  `unverified`.
- Migrations touch a PII-adjacent area; test locally first, back up before
  schema change (per CLAUDE.md). New table only — no alter of contact/lead PII
  columns.
- Keep all new heavy I/O inside workers (single-process worker model); the
  search/reveal API must not block on crawling.

## Verification plan

- `make ci.backend` (ruff + mypy + pytest) for new services/models/workers.
- New unit tests: email pattern generation, signal aggregation scoring, people
  HTML extraction (fixture HTML), dedupe person facet, search filter SQL.
- `make migrate` locally, then `.ezcoder/eyes/http.sh` against
  `/api/v1/workspaces/{id}/prospects/search` and `/readyz` to confirm no 500s.
- `.ezcoder/eyes/logs.sh --service backend --grep "people_discovery|signals|ERROR|Traceback"`
  after triggering a `web_people` discovery job.
- `make ci.codegen` to regenerate `backend/openapi.json` +
  `frontend/src/lib/api/_generated.ts` after new routes/schemas land.
- `make ci.frontend` for the new People Search page.

## Out of scope for v1 (follow-up phases)

- Licensed `people_db` provider implementation (seam only in v1).
- Hiring/funding signal *data sources* (provider stubs + model only in v1).
- SMTP-based verification at scale / provider waterfall (MX + opt-in only).
- Intent/web-visitor and job-change signals.

## Steps

1. Add a DB migration + ORM model `ProspectSignal`
   (`backend/app/models/prospect_signal.py`): workspace_id, prospect_id (FK,
   cascade), `signal_type` (str, e.g. `running_ads`, `ad_tech`, `hiring`,
   `funding`), `strength` (int 0–100), `status`, `observed_at`, `source`,
   `payload` JSONB, with `(workspace_id, prospect_id, signal_type)` unique and
   indexes on `(workspace_id, signal_type, strength desc)`. Register in
   `app/models/__init__.py`; generate via `make migrate.new`.
2. Extend `DiscoverySourceType` / dedupe: add a `dedupe_key_for_person` helper
   in `backend/app/services/lead_discovery/dedupe.py` (email facet, else
   name+host facet) and export it; add `ProspectIdentityKind` usage for person
   rows. No change to existing key semantics.
3. Create `backend/app/services/signals/` package: `protocol.py`
   (`SignalProvider` with `collect(prospect) -> list[CollectedSignal]`),
   `types.py` (`CollectedSignal` dataclass), and `aggregator.py` that runs
   enabled providers, upserts `ProspectSignal` rows, and folds signal strength
   into `LeadProspect.lead_score` + appends outreach evidence.
4. Implement `AdsSignalProvider` in `signals/providers/ads.py` that maps an
   advertiser already linked to the prospect (via `ad_intelligence`) into a
   `running_ads` `CollectedSignal` using `opportunity_score`,
   `longest_running_active_days`, and `example_creative`.
5. Implement `AdTechSignalProvider` in `signals/providers/ad_tech.py` using
   `WebsiteScraperService._detect_ad_pixels` output (meta_pixel/google_ads/etc.)
   to emit an `ad_tech` signal ("running Meta + Google pixels"); reuse the
   scraper instance from the enrichment worker.
6. Add config-gated `HiringSignalProvider` + `FundingSignalProvider` stubs in
   `signals/providers/` that return `[]` unless their API keys are configured
   (new settings in `core/config.py`, defaulting empty/off). No fabricated data.
7. Add a pure `backend/app/services/lead_discovery/email_patterns.py`:
   `candidate_emails(first, last, domain)` returning ranked patterns
   (`first.last@`, `first@`, `flast@`, …) with confidence weights.
8. Add config-gated `backend/app/services/lead_discovery/email_verifier.py`:
   MX lookup always; SMTP/provider probe behind `email_verification_enabled`
   (new setting, default False). Returns `(status, confidence)` and never raises
   into callers.
9. Implement the people-extraction provider
   `backend/app/services/lead_discovery/providers/web_people.py`
   (`source_type="web_people"`): given a domain (or company list from a query via
   `GooglePlacesLeadProvider`), crawl a bounded set of team/about/staff/contact
   pages with `WebsiteScraperService`, extract people (name + title) via a
   parser + `ai_content_analyzer` fallback, infer emails via `email_patterns`,
   and emit one `RawLead` per person with `source_metadata` confidence. Enforce a
   per-domain page cap and `scraping_limiter`.
10. Wire `web_people` into discovery-job execution: add a
    `run_people_discovery_job` path (mirror `ad_intelligence/discovery.py`) that
    persists `LeadProspect` rows via the existing dedupe→upsert flow and stamps
    provenance; route it from the discovery worker based on `source_type`.
11. Extend `ProspectEnrichmentWorker`: after tracing, run the signals
    `aggregator` for the prospect and, when no verified email exists, generate
    candidates (`email_patterns`) and verify (`email_verifier`), writing
    `LeadEnrichmentResult` audit rows and the chosen email + verification status.
12. Add the people-discovery worker spec/flag: new `web_people` discovery worker
    (or extend the existing discovery worker) registered in
    `backend/app/workers/__init__.py` with an `enabled_setting`, plus the new
    config flags in `core/config.py`.
13. Add Pydantic schemas in `backend/app/schemas/`: `ProspectSignalResponse`,
    `PeopleSearchRequest` (filters: title/seniority/keywords, location,
    industry, has_email, has_phone, signal_types, min_score, page), and a
    `PeopleDiscoveryRequest` for launching a `web_people` job.
14. Add a workspace-scoped router `backend/app/api/v1/prospects.py`: `POST
    /workspaces/{id}/prospects/search` (cross-mission people search with signal
    filters, ranked by score), `POST /prospects/{id}/reveal-email` (on-demand
    pattern+verify), `POST /prospects/people-discovery` (launch `web_people`
    job), and `POST /prospects/{id}/add-to-mission`. Register in
    `app/api/v1/router.py`; use `ServiceErrorRoute` + `WorkspaceAccess`.
15. Add a `ProspectSearchService` in `backend/app/services/contacts/` (or
    `lead_discovery/`) that builds the filtered, signal-joined, score-ranked SQL
    query and the reveal/add-to-mission operations, workspace-scoped.
16. Backend tests under `backend/tests/`: email pattern generation, signal
    aggregation + score folding, `web_people` extraction from fixture HTML,
    person dedupe key, and the search-filter query. Run `make ci.backend`.
17. Run `make migrate` locally then verify with
    `.ezcoder/eyes/http.sh http://localhost:8000/api/v1/.../prospects/search`
    and `/readyz`; check `.ezcoder/eyes/logs.sh --service backend` for tracebacks
    after launching a `web_people` job.
18. Run `make ci.codegen` to regenerate `backend/openapi.json` +
    `frontend/src/lib/api/_generated.ts`; commit both.
19. Frontend: add query-keys (`peopleSearch`, `prospectSignals`) and a
    `/find-leads/people` route + client following the `find-leads/ad-library`
    patterns — Apollo-style filter panel (title/seniority/location/industry/
    has-email/signal chips incl. "Running ads"), results table with signal
    badges, reveal-email button, and bulk "Add to mission". Use `page-state` for
    loading/error/empty.
20. Run `make ci.frontend`; capture a screenshot of `/find-leads/people` for
    visual confirmation, then summarize shippable v1 vs. the gated follow-ups
    (licensed `people_db`, hiring/funding data, SMTP verification at scale).
