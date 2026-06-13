"""Crawl orchestration for the phone-reveal flow (I/O).

Given a company domain, fetch a small bounded set of the company's own
first-party pages (homepage + common contact/about paths) via
:class:`WebsiteScraperService`, run the pure :func:`extract_phone_candidates` on
each, and merge + rank the results into best-effort business-line candidates.

Compliance mirrors :mod:`providers.web_people`: first-party pages only, a polite
inter-fetch delay, and a hard page cap. Like :func:`email_verifier.verify_email`,
this **never raises into its caller** — any scraper failure degrades to ``[]``.
"""

from __future__ import annotations

import asyncio

import structlog

from app.services.lead_discovery.dedupe import extract_host
from app.services.lead_discovery.phone_extract import (
    PhoneCandidate,
    extract_phone_candidates,
)
from app.services.scraping.website_scraper import (
    WebsiteScraperError,
    WebsiteScraperService,
)

logger = structlog.get_logger()

# First-party paths most likely to publish a business phone number, in priority
# order. The homepage is always fetched first; these fill the remaining budget.
_CONTACT_PATHS: tuple[str, ...] = ("/contact", "/contact-us", "/about", "/about-us")

_INTER_FETCH_DELAY_SECONDS = 0.5


async def find_phone_candidates(
    domain: str,
    *,
    scraper: WebsiteScraperService,
    max_pages: int,
    country: str = "US",
) -> list[PhoneCandidate]:
    """Crawl ``domain`` for published phone numbers. Never raises.

    Fetches the homepage plus up to ``max_pages`` total first-party pages
    (drawing from common contact/about paths), extracts candidates from each,
    and returns them merged, de-duplicated by E.164, and ranked by confidence.
    Returns ``[]`` when the domain can't be resolved or nothing is found.
    """
    host = extract_host(domain)
    if not host or max_pages <= 0:
        return []

    log = logger.bind(component="phone_finder", domain=host)
    urls = [f"https://{host}", *(f"https://{host}{path}" for path in _CONTACT_PATHS)]

    best: dict[str, PhoneCandidate] = {}
    pages_fetched = 0
    for url in urls:
        if pages_fetched >= max_pages:
            break
        if pages_fetched > 0 and _INTER_FETCH_DELAY_SECONDS > 0:
            await asyncio.sleep(_INTER_FETCH_DELAY_SECONDS)
        try:
            result = await scraper.scrape_website(url)
        except WebsiteScraperError as exc:
            # Contact/about paths often 404 — that's expected, not an error.
            log.debug("phone_fetch_failed", url=url, error=str(exc))
            continue
        pages_fetched += 1
        html = result.get("html_content")
        if not isinstance(html, str):
            continue
        for candidate in extract_phone_candidates(html, url, country):
            existing = best.get(candidate.phone)
            if existing is None or candidate.confidence > existing.confidence:
                best[candidate.phone] = candidate

    ranked = sorted(best.values(), key=lambda c: c.confidence, reverse=True)
    log.info("phone_finder_complete", pages=pages_fetched, candidates=len(ranked))
    return ranked
