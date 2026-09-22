# People Search — Phone Number Finder

Add an on-demand **"Reveal phone"** action to People Search that mirrors the
existing **"Reveal email"** flow, plus the supporting backend extraction.

## The honest reality (read first)

Email reveal works because a personal email is **deterministically inferable**
from `name + domain` (`first.last@acme.com`) and then MX/SMTP-verifiable. **Phone
numbers cannot be inferred that way** — there's no pattern from a name to a phone
number.

So a no-paid-API phone finder can only do one realistic thing: **scrape the
prospect's own company website (homepage + contact/about pages) for phone numbers
and attach the best business line(s).** That means:

- It returns a **business / main line**, usually not the person's direct dial.
- It "pulls a few to try" — ranked candidates, best-effort, sometimes empty.
- This matches the user's framing ("even if it pulls a few to try").

A true per-person direct-dial finder requires a paid people-data provider
(Apollo / Hunter / Lusha). That is **out of scope here** and noted as a future,
config-gated enhancement (`email_finder_provider` config already exists as the
analogous hook).

We already have the plumbing: `LeadProspect.phone_number` (encrypted) +
`phone_hash` (lookup) + `has_phone` property + `has_phone` search filter +
`EnrichmentProvider.PHONE_LOOKUP` + `normalize_phone_safe()` /
`validate_phone_number()` in `app/utils/phone.py`. Nothing populates phone for
the `web_people` path today — this plan fills that gap.

## Design (mirror reveal-email exactly)

Reference flow being mirrored:
- Pure inference: `app/services/lead_discovery/email_patterns.py::candidate_emails`
- I/O verify: `app/services/lead_discovery/email_verifier.py::verify_email`
- Orchestration: `ProspectSearchService.reveal_email` (schemas + audit row + commit)
- Route: `app/api/v1/prospects.py::reveal_email`
- Client: `frontend/src/lib/api/people.ts::peopleApi.revealEmail`
- UI: `PersonRow` email cell + `revealMutation` in `people-client.tsx`

### Backend pieces

1. **Pure extraction** — `backend/app/services/lead_discovery/phone_extract.py` (no I/O):
   - `@dataclass(frozen=True) PhoneCandidate { phone: str (E.164), source: str, confidence: int, source_url: str | None }`
   - `extract_phone_candidates(html, source_url=None, default_country="US") -> list[PhoneCandidate]`:
     - Parse with `BeautifulSoup`.
     - High-confidence: `a[href^="tel:"]` hrefs (confidence ~85).
     - Medium-confidence: run `phonenumbers.PhoneNumberMatcher(text, region)` over
       the page's visible text (confidence ~55).
     - Normalize each via `normalize_phone_safe`; drop anything that fails
       `validate_phone_number`; dedupe by E.164 keeping highest confidence; sort
       descending. Mirror the shape/return-contract of `candidate_emails`.

2. **Crawl orchestration** — `backend/app/services/lead_discovery/phone_finder.py` (I/O):
   - `async def find_phone_candidates(domain, *, scraper: WebsiteScraperService, max_pages: int, country="US") -> list[PhoneCandidate]`:
     - Fetch `https://{host}` via `scraper.scrape_website()` (reuse, returns `html_content`).
     - Try a small bounded set of common contact paths (`/contact`, `/contact-us`,
       `/about`, `/about-us`) up to `max_pages`, first-party only, polite delay
       (mirror `WebPeopleLeadProvider._fetch`).
     - Run `extract_phone_candidates` on each page, merge + rank + cap.
     - Degrade to `[]` on `WebsiteScraperError` (never raise into caller), mirroring
       `verify_email` never raising.

3. **Service** — add `ProspectSearchService.reveal_phone(workspace_id, prospect_id, *, scraper=None) -> RevealPhoneResponse`:
   - `_get_prospect_or_404`; resolve `domain = website_host or extract_host(website_url)`;
     `ValidationError` if none (mirror reveal_email).
   - If `not settings.phone_reveal_enabled`: return empty response (no crawl).
   - Call `find_phone_candidates`. Choose top candidate.
   - Persist **only if** `prospect.phone_hash` is None: set `phone_number` +
     `phone_hash = hash_value(e164)` (never overwrite an existing phone).
   - Update `provenance`: `phone_source`, `phone_status` ("found"/"not_found"),
     `phone_candidates` (top 5).
   - Write `LeadEnrichmentResult(provider=PHONE_LOOKUP, status=SUCCESS if found else SKIPPED, extracted={...}, response_payload={domain, source:"reveal_phone"})`.
   - `await self._db.commit()`; return `RevealPhoneResponse`.
   - `scraper` param is injectable for tests (mirror `WebPeopleLeadProvider(scraper=...)`).

4. **Schema** — `backend/app/schemas/prospect_search.py`, add:
   ```python
   class RevealPhoneResponse(BaseModel):
       prospect_id: uuid.UUID
       phone_number: str | None
       source: str | None
       candidates: list[dict[str, Any]] = Field(default_factory=list)
   ```

5. **Config** — `backend/app/core/config.py`, in the people-discovery block:
   - `phone_reveal_enabled: bool = True`
   - `phone_reveal_max_pages: int = 3`

6. **Route** — `backend/app/api/v1/prospects.py`, add
   `POST /{prospect_id}/reveal-phone` → `RevealPhoneResponse`. Because it does live
   crawling, call `await enforce_scraping_rate_limit(workspace_id)` first (like
   `launch_people_discovery`), then `service.reveal_phone(...)`.

7. **Codegen** — `make ci.codegen` to regenerate `backend/openapi.json` +
   `frontend/src/lib/api/_generated.ts` (adds `RevealPhoneResponse` + the route).

### Frontend pieces

8. **API client** — `frontend/src/lib/api/people.ts`:
   - `export type RevealPhoneResponse = Schemas["RevealPhoneResponse"];`
   - `peopleApi.revealPhone(workspaceId, prospectId)` → `POST .../prospects/{id}/reveal-phone`
     (mirror `revealEmail`).

9. **UI** — `frontend/src/app/find-leads/people/people-client.tsx`:
   - Add `revealPhoneMutation` mirroring `revealMutation` (toast with number +
     source on success; "No phone could be found." on empty; invalidate
     `queryKeys.people.search`).
   - Add a **Phone** column: `<TableHead>Phone</TableHead>` between Email and Score.
   - In `PersonRow`: if `person.has_phone && person.phone_number` show it; else a
     `Reveal` button (Phone icon) calling `onRevealPhone`, with per-row spinner
     (mirror the email cell). Add `onRevealPhone` / `revealingPhone` props.
   - Toast/empty-state copy should say "business line" to set accurate expectations.

### Tests

10. `backend/tests/services/lead_discovery/test_phone_extract.py` (pure): tel: link
    extraction, text-number extraction via `PhoneNumberMatcher`, invalid numbers
    dropped, dedupe by E.164, descending-confidence ordering, empty HTML → `[]`.
    Mirror `test_email_patterns.py`.

11. Extend `backend/tests/services/lead_discovery/test_prospect_search_service.py`
    with `test_reveal_phone_*`: inject a fake scraper returning canned HTML with a
    `tel:` link; assert the persisted `phone_hash == hash_value(e164)`,
    `provenance["phone_source"]`, and that an existing phone is never overwritten.
    Mirror `test_reveal_email_infers_and_persists`.

### Manual verification (eyes)

12. Re-seed (`backend/scripts/dev/seed_people_search_e2e.py`), then:
    - API: `.ezcoder/eyes/http.sh http://localhost:8000/api/v1/workspaces/<ws>/prospects/<id>/reveal-phone POST {} -H "Authorization: Bearer <token>"`
      against a seeded person whose domain resolves; confirm 200 + response shape,
      and a 4xx for a prospect with no domain.
    - Logs: `.ezcoder/eyes/logs.sh --file .ezcoder/eyes/out/backend.log --grep "reveal_phone|PHONE_LOOKUP|ERROR|Traceback"`.
    - UI: screenshot the People Search results table showing the new **Phone**
      column + a successful reveal toast (via the login→navigate→click flow used
      previously).

## Risks & constraints

- **Live CRM data**: reveal persists a phone onto a real prospect. Mitigated by
  only filling when `phone_hash` is empty (never overwrite) and workspace-scoping
  every read/write (mirror reveal_email).
- **Live HTTP crawl**: gated by `phone_reveal_enabled` and `enforce_scraping_rate_limit`;
  first-party pages only (same compliance posture as `web_people`); never raises.
- **Accuracy**: business line, not personal direct dial — must be reflected in UI
  copy and `provenance.phone_source` so operators aren't misled.
- **Scope discipline**: no paid provider, no new dependency (`phonenumbers` and
  `beautifulsoup4` are already deps), no auto-phone-extraction during the
  `web_people` crawl in this pass (possible cheap follow-up since pages are
  already fetched there).

## Steps

1. Add pure `backend/app/services/lead_discovery/phone_extract.py` with `PhoneCandidate` + `extract_phone_candidates(html, source_url, default_country)` (tel: links + `phonenumbers.PhoneNumberMatcher`, normalize/validate/dedupe/rank).
2. Add `backend/app/services/lead_discovery/phone_finder.py` with `find_phone_candidates(domain, *, scraper, max_pages, country)` that crawls homepage + bounded contact/about paths via `WebsiteScraperService` and merges candidates, degrading to `[]` on scraper errors.
3. Add `RevealPhoneResponse` to `backend/app/schemas/prospect_search.py`.
4. Add `phone_reveal_enabled: bool = True` and `phone_reveal_max_pages: int = 3` to `backend/app/core/config.py`.
5. Add `ProspectSearchService.reveal_phone(workspace_id, prospect_id, *, scraper=None)` to `backend/app/services/lead_discovery/prospect_search_service.py`, mirroring `reveal_email` (404, domain resolution, gate, crawl, persist-if-empty, provenance, `PHONE_LOOKUP` audit row, commit).
6. Add `POST /{prospect_id}/reveal-phone` route to `backend/app/api/v1/prospects.py` with `enforce_scraping_rate_limit` then `service.reveal_phone`.
7. Run `make ci.codegen` to regenerate `backend/openapi.json` and `frontend/src/lib/api/_generated.ts`.
8. Add `RevealPhoneResponse` type + `peopleApi.revealPhone` to `frontend/src/lib/api/people.ts`.
9. Add a Phone column, `revealPhoneMutation`, and per-row Reveal-phone button/props to `frontend/src/app/find-leads/people/people-client.tsx` (with "business line" copy).
10. Add `backend/tests/services/lead_discovery/test_phone_extract.py` covering tel: links, text numbers, invalid drop, dedupe, ordering, empty HTML.
11. Extend `backend/tests/services/lead_discovery/test_prospect_search_service.py` with `reveal_phone` tests using an injected fake scraper, asserting persistence and no-overwrite.
12. Verify end-to-end: re-seed, hit `/reveal-phone` via `.ezcoder/eyes/http.sh`, scan `backend.log` for `PHONE_LOOKUP`/tracebacks, and screenshot the Phone column + reveal toast in the UI.
