# In-House Meta Ad Library Scraper (own the data source, no paid third party)

## Goal

Replace the dependency on a paid third-party ad API with our own scraper that
pulls **US commercial** advertisers from Meta's public Ad Library, so the
existing discover → rank → promote → CRM → call pipeline gets real, live
advertisers to work. The official `/ads_archive` API only returns
political/issue ads (proven live: it returned Graph error code 10 for our
commercial roofing search), so the data must come from the same public surface
the Ad Library website itself uses.

## Research findings (grounding)

### Why this is even possible
- The Ad Library **website** is public, no login, and renders commercial ads.
  It is powered by an internal endpoint `POST https://www.facebook.com/ads/library/async/search_ads/`
  that returns `for (;;);`-prefixed JSON with ads under `payload.results`
  (verified pattern: `megadose/facebook_totem` `core.py`, and the
  `openclaw/skills` ad-intelligence reference).
- Page-name → numeric page id resolves via a sibling endpoint
  `async/search_typeahead/` (`payload.pageResults`).

### The single biggest head start (reuse, don't rebuild)
- `backend/app/services/ad_intelligence/providers/meta_thirdparty.py` **already
  normalizes Meta's internal ad shape** — it reads `ad_archive_id`/`adArchiveID`,
  `snapshot.body.text`, `snapshot.cards[]`, `snapshot.link_url`,
  `snapshot.display_format`, `start_date`/`end_date` epochs, `is_active`,
  `publisher_platform`. That is exactly the JSON the public `search_ads`
  endpoint returns. So the new scraper's **normalization is ~90% already
  written**; we mostly need the *fetch + token + pagination* layer and to feed
  raw ad dicts into the same `_group_advertisers`/`_normalize_ad` logic.
- Everything downstream is already provider-agnostic: `AdStore` (upsert),
  `signals.py` (ICP scoring), `prospecting.py` (→ LeadProspect),
  `promotion.py` (→ Contact), and the `AdLibraryDiscoveryWorker`. A new
  provider only has to emit `AdProviderResult` (advertisers + `NormalizedAd`s).

### The 2026 anti-bot reality (this is the real risk, not the parsing)
- Meta's Ad Library is rated "Very Difficult (5/5)" for scraping due to a custom
  WAF; the public surface stays accessible **but** the internal endpoint now
  requires a valid **LSD CSRF token + session cookies** harvested by first
  loading `https://www.facebook.com/ads/library/`, and increasingly a
  **residential proxy** — datacenter IPs get 403 / login-redirect / challenge
  pages. (Sources: Apify `harvestlab` actor notes; scraperly 2026 anti-bot
  guide.) Our production backend runs on **Railway (a datacenter IP)**, so the
  scraper will very likely be blocked from prod without a residential/ISP proxy.
- Two viable fetch strategies, in order of robustness:
  1. **Token-bootstrapped HTTP** (lightweight, no browser dep): GET the Ad
     Library page, regex the `LSD` token + `datr`/session cookies out of the
     HTML, then POST `async/search_ads/` reusing them. Cheapest; most brittle to
     WAF/markup changes. (facebook_totem pattern, modernized with the LSD token.)
  2. **Headless-browser GraphQL intercept** (heavier, more robust): drive a
     headless Chromium to the Ad Library URL and capture the GraphQL/`search_ads`
     JSON responses as they load. Survives token/markup churn because a real
     browser produces the tokens. Needs Playwright/Chromium — which the repo
     **already gates** behind `ad_library_snapshot_rendering_enabled` and is
     installed for the screenshot eyes. (crawl4ai / agent-browser / Selenium
     patterns.)

### Compliance posture already in the codebase (must honor)
- `backend/app/services/ad_intelligence/compliance.py` has
  `ensure_raw_scrape_allowed(context)` which **raises unless
  `settings.ad_library_allow_raw_scrape` is true** (default false), explicitly
  citing *Meta v. Bright Data* and ToS restrictions. The new provider MUST call
  this gate so raw scraping stays opt-in and auditable, exactly like the design
  intended. This is the difference between "a feature behind a flag the operator
  consciously enables" and "we silently scrape Meta."

## Architecture decision

Add a new provider `MetaScraperProvider` (platform `"meta"`) that:
- Is selected by the factory when the operator opts into self-scraping
  (`meta_self_scrape_enabled` + `ad_library_allow_raw_scrape`), preferred over
  the official provider for the `meta` platform when on.
- Has a pluggable **fetch strategy**: `token_http` (default, no browser) or
  `headless` (Playwright, behind the existing snapshot/render flag).
- Reuses the existing internal-shape normalization by extracting the pure
  helpers from `meta_thirdparty.py` into a shared module so both providers share
  one normalizer (no copy-paste).
- Goes through the **same** rate limiter, `AdStore`, signal engine, and worker —
  zero changes to persistence/scoring/promotion.

Why a new provider and not editing `meta_thirdparty.py`: that class is the
"licensed API wrapper" abstraction (key + base_url to a vendor). Self-scraping
has different config, a token/cookie lifecycle, proxy needs, and a hard
compliance gate. Keeping them separate keeps each one honest and testable.

## Files

### New
- `backend/app/services/ad_intelligence/providers/meta_scraper.py` —
  `MetaScraperProvider`. Owns: token/cookie bootstrap, `search_ads` +
  `search_typeahead` calls, `for (;;);` stripping, cursor pagination
  (`forward_cursor`/`collation_token`/`session_id` echoed back from each page),
  proxy support, jittered backoff on 429/403, and the
  `ensure_raw_scrape_allowed()` gate. Delegates ad-dict → `NormalizedAd`/
  `NormalizedAdvertiser` to the shared normalizer.
- `backend/app/services/ad_intelligence/providers/_meta_internal_shape.py` —
  shared pure normalizer extracted from `meta_thirdparty.py`
  (`_normalize_ad`, `_group_advertisers` body, `_dig`/`_str`/`_parse_epoch`/
  `_best_landing`/`_caption_to_url`). Both `meta_thirdparty.py` and
  `meta_scraper.py` import it. No behavior change to the third-party provider.
- `backend/app/services/ad_intelligence/scraper_session.py` — token/cookie
  bootstrap + (optional) headless strategy. `TokenHttpSession` loads the Ad
  Library page once, extracts LSD + cookies, caches them in Redis with a short
  TTL (reuse across calls within the hour budget), and refreshes on 401/403.
  `HeadlessSession` (only imported when `headless` strategy selected) drives
  Playwright Chromium and captures `search_ads` responses.
- `backend/tests/services/ad_intelligence/test_meta_scraper_provider.py` —
  `httpx.MockTransport` serving a recorded `for (;;);`+`payload.results`
  fixture (mirrors the existing `test_meta_ad_library_provider.py` harness; no
  real Facebook traffic). Covers: token bootstrap, `for (;;);` stripping,
  page-name typeahead resolution, normalization parity with the internal shape,
  pagination via echoed cursor, 403→re-bootstrap-once, compliance-gate raise
  when `ad_library_allow_raw_scrape` is false.
- `backend/tests/services/ad_intelligence/fixtures/meta_search_ads_page1.json`,
  `..._page2.json` — recorded sample payloads (sanitized, no tokens).

### Modified
- `backend/app/core/config.py` — add: `meta_self_scrape_enabled: bool = False`,
  `meta_scrape_strategy: str = "token_http"` (`token_http` | `headless`),
  `meta_scrape_proxy_url: str = ""`, `meta_scrape_min_delay_seconds: float = 2.0`,
  `meta_scrape_max_delay_seconds: float = 5.0`,
  `meta_scrape_session_ttl_seconds: int = 1800`. (Keep the existing
  `ad_library_allow_raw_scrape` hard gate as the master switch.)
- `backend/.env.example` — add the new keys (blank/defaults) so `make ci.env`
  (`scripts/dev/check_env_drift.py`) passes; it diffs config fields against the
  template.
- `backend/app/services/ad_intelligence/provider_factory.py` — in `_build_meta`,
  before the official-token branch: if `settings.meta_self_scrape_enabled and
  settings.ad_library_allow_raw_scrape` (or per-workspace integration opts in),
  return `MetaScraperProvider(...)`. Order: explicit third-party key → self-scrape
  (if enabled) → official token → raise. Keeps official API as a fallback.
- `backend/app/services/ad_intelligence/providers/meta_thirdparty.py` — replace
  its private helpers with imports from `_meta_internal_shape.py` (pure refactor,
  guarded by its existing tests).
- `backend/app/services/ad_intelligence/compliance.py` — no logic change; the
  new provider calls `ensure_raw_scrape_allowed("meta_self_scrape")`. Optionally
  add a tiny `ensure_self_scrape_allowed()` wrapper for a clearer audit label.
- `backend/app/services/ad_intelligence/rate_limit.py` — add a distinct, much
  lower default cap for the scrape path (e.g. `meta_scrape_rate_limit_per_hour`,
  reuse `acquire_provider_call_slot(platform, cap=...)`). Scraping must be
  gentler than the 200/hr official tier to avoid WAF bans.
- `backend/docs/` — short operator note: what self-scraping is, the ToS/risk
  posture, why a residential proxy is needed on Railway, how to enable.

### Explicitly NOT changing
- `ad_store.py`, `signals.py`, `prospecting.py`, `promotion.py`,
  `discovery.py`, `ad_library_discovery_worker.py`, the schemas, the API
  router, and the entire frontend. The new data source flows through the
  existing rails unchanged. (Frontend already has the search form + ICP toggles;
  no UI change needed to consume scraped advertisers.)

## Risks & honest caveats (read before approving)

1. **Terms of Service.** Programmatic scraping of `facebook.com/ads/library`
   is against Meta's ToS, regardless of the data being "public" (cf. *Meta v.
   Bright Data*, which Meta lost on the public-data point but which still left
   ToS/▒account-based claims alive). This is why it stays behind
   `ad_library_allow_raw_scrape` and is operator-enabled, never default. Owning
   the code does not remove the ToS question — you are accepting that risk
   consciously. Not legal advice.
2. **Production (Railway) will likely be blocked** without a residential/ISP
   proxy — datacenter IPs draw 403/login challenges. Plan includes
   `meta_scrape_proxy_url`, but a proxy is itself an external dependency you may
   end up paying for. The "no third party" goal is mostly achievable for the
   *parsing/pipeline*; the *network egress* may still need a paid proxy to be
   reliable at scale. Local/dev works from a residential IP without one.
3. **Brittleness.** Token names, the `search_ads` param set, and the response
   shape change without notice. Mitigations: the `headless` strategy (real
   browser makes tokens), recorded-fixture tests to catch shape drift fast, and
   keeping the official API as an automatic fallback so a scrape break degrades
   instead of hard-failing.
4. **Throughput.** Gentle rate limiting + jitter is mandatory; this is a
   "tens-to-low-hundreds of advertisers per run" tool, not a firehose. That is
   still plenty for daily sales prospecting.
5. **Phone-number gate still applies.** Even with live advertisers, promotion
   still requires a scrapeable phone (existing `promotion.py` behavior). This
   plan fixes *supply of advertisers*, not the separate phone-coverage gap.

## Verification

- `backend/tests/.../test_meta_scraper_provider.py` green (MockTransport, no
  real traffic) — normalization parity, pagination, token re-bootstrap,
  compliance gate.
- `make ci.backend` (ruff, mypy, pytest, coverage) and `make ci.env` (env-drift
  for the new config keys) pass.
- Local live smoke (residential IP, dev only, behind the flag): enable
  `ad_library_allow_raw_scrape=true` + `meta_self_scrape_enabled=true`, run a
  `roofing` search via the existing `/search` endpoint, confirm the discovery
  worker produces real `AdAdvertiser` rows, then promote one and confirm a CRM
  Contact — same end-to-end path already verified with seed data, now with live
  scraped data. Capture via `.ezcoder/eyes/http.sh` + a UI screenshot.
- Do **not** smoke-test against prod/Railway in this change; document the proxy
  requirement instead.

## Steps

1. Create `_meta_internal_shape.py` by extracting the pure normalization
   helpers (`_normalize_ad`, advertiser grouping, `_dig`/`_str`/`_parse_epoch`/
   `_best_landing`/`_caption_to_url`, `_DISPLAY_FORMAT_MEDIA`) from
   `meta_thirdparty.py`, with no behavior change.
2. Refactor `meta_thirdparty.py` to import those helpers from the new shared
   module; keep its public behavior identical (its existing tests are the guard).
3. Add the new settings fields to `backend/app/core/config.py`
   (`meta_self_scrape_enabled`, `meta_scrape_strategy`, `meta_scrape_proxy_url`,
   `meta_scrape_min/max_delay_seconds`, `meta_scrape_session_ttl_seconds`,
   `meta_scrape_rate_limit_per_hour`) and mirror them in `backend/.env.example`.
4. Implement `scraper_session.py` with `TokenHttpSession` (load Ad Library page,
   extract LSD token + cookies, cache in Redis with TTL, refresh on 401/403,
   optional proxy) and a lazily-imported `HeadlessSession` (Playwright capture).
5. Implement `MetaScraperProvider` in `meta_scraper.py`: call
   `ensure_raw_scrape_allowed`, resolve page-name via `search_typeahead`, POST
   `search_ads`, strip the `for (;;);` prefix, paginate via the echoed
   `forward_cursor`/`collation_token`/`session_id`, apply jittered backoff on
   429/403, and hand raw ad dicts to the shared normalizer to build
   `AdProviderResult`.
6. Wire selection in `provider_factory._build_meta`: prefer self-scrape when
   `meta_self_scrape_enabled and ad_library_allow_raw_scrape` (or workspace
   integration opt-in), keeping the official token path as automatic fallback.
7. Add a distinct, lower scrape rate-limit cap in `rate_limit.py` and use it on
   the scrape path via `acquire_provider_call_slot(..., cap=...)`.
8. Add recorded JSON fixtures and `test_meta_scraper_provider.py` using
   `httpx.MockTransport`; cover token bootstrap, `for (;;);` stripping,
   typeahead resolution, normalization parity, cursor pagination, 403
   re-bootstrap, and the compliance-gate raise when the flag is off.
9. Run `make ci.backend` and `make ci.env`; fix lint/type/coverage/env-drift.
10. Local live smoke behind the flags from a residential IP: run a `roofing`
    `/search`, confirm real advertisers land, promote one to a CRM contact, and
    capture `.ezcoder/eyes/http.sh` output + a UI screenshot.
11. Add the operator/risk note under `backend/docs/` (ToS posture, proxy
    requirement on Railway, how to enable), and leave all flags **off by
    default**.
