"""In-house self-scrape provider for the public Meta Ad Library.

Owns the data source instead of paying a third party: it calls the **same**
internal GraphQL endpoint the Ad Library *website* uses
(``POST .../api/graphql/`` with the ``AdLibrarySearchPaginationQuery`` persisted
query), which returns commercial US ads the official ``/ads_archive`` API does
not (that endpoint is political/issue only for non-EU commercial searches).
Page-name lookups resolve through the typeahead persisted query.

.. note::
   The older ``async/search_ads/`` / ``async/search_typeahead/`` form endpoints
   were retired by Meta (HTTP 404). This provider targets ``/api/graphql/``.

This provider is **hard-gated** behind ``ad_library_allow_raw_scrape`` via
:func:`app.services.ad_intelligence.compliance.ensure_self_scrape_allowed` so
raw scraping stays opt-in and auditable (cf. *Meta v. Bright Data* + Meta ToS).
It is selected by the factory only when the operator also flips
``meta_self_scrape_enabled``.

Division of labour:

* :mod:`app.services.ad_intelligence.scraper_session` owns the LSD/DTSG token /
  cookie / JS-challenge / transport lifecycle (``token_http`` or ``headless``).
  Live scraping requires ``headless`` to clear the initial JS challenge.
* This module owns GraphQL ``variables`` shaping, cursor pagination, gentle
  jittered pacing, and hands raw ad dicts to the shared internal-shape
  normalizer in
  :mod:`app.services.ad_intelligence.providers._meta_internal_shape` — the same
  one the licensed third-party provider uses, so normalization never drifts.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from typing import Any, ClassVar

import httpx
import structlog

from app.core.config import settings
from app.services.ad_intelligence.compliance import ensure_self_scrape_allowed
from app.services.ad_intelligence.protocol import BaseAdIntelligenceProvider
from app.services.ad_intelligence.providers._meta_internal_shape import flatten, group_advertisers
from app.services.ad_intelligence.rate_limit import acquire_scrape_call_slot
from app.services.ad_intelligence.scraper_session import ScrapeSession, build_session
from app.services.ad_intelligence.types import (
    AdProviderResult,
    AdSearchRequest,
    DiscoveryWarning,
)
from app.services.lead_discovery.errors import LeadDiscoveryRateLimitError

logger = structlog.get_logger()

PLATFORM = "meta"
# The endpoint returns ~30 ads per page regardless of a higher count hint.
_PAGE_SIZE = 30
# Relay ``fb_api_req_friendly_name`` values for the persisted queries the Ad
# Library website issues. The matching ``doc_id`` values live in settings
# (Meta rotates them); see ``meta_scrape_search_doc_id`` / ``_typeahead_doc_id``.
_SEARCH_FRIENDLY_NAME = "AdLibrarySearchPaginationQuery"
_TYPEAHEAD_FRIENDLY_NAME = "useAdLibraryTypeaheadSuggestionDataSourceQuery"
# Schema version hash Meta's client pins alongside the search ``doc_id`` (from
# live traffic 2026-06-12); sent verbatim in the search ``variables`` blob.
_SEARCH_VARIABLES_VERSION = "9d1187"


class MetaScraperProvider(BaseAdIntelligenceProvider):
    """Self-scrape adapter over the Ad Library website's internal endpoints."""

    platform: ClassVar[str] = PLATFORM

    def __init__(
        self,
        *,
        session: ScrapeSession | None = None,
        strategy: str | None = None,
        proxy_url: str | None = None,
        min_delay_seconds: float | None = None,
        max_delay_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the self-scrape provider.

        Args:
            session: Injected :class:`ScrapeSession` (tests/DI). When omitted one
                is built from ``meta_scrape_strategy`` + ``meta_scrape_proxy_url``.
            strategy: Override the scrape strategy (``token_http`` | ``headless``).
            proxy_url: Override the residential/ISP proxy URL.
            min_delay_seconds / max_delay_seconds: Jittered inter-page delay
                bounds; fall back to settings. Pass ``0`` to disable in tests.
            client: Optional injected ``httpx.AsyncClient`` for the token_http
                session (tests/DI).
        """
        self._session = session or build_session(
            strategy=strategy, proxy_url=proxy_url, client=client
        )
        self._min_delay = (
            min_delay_seconds
            if min_delay_seconds is not None
            else settings.meta_scrape_min_delay_seconds
        )
        self._max_delay = (
            max_delay_seconds
            if max_delay_seconds is not None
            else settings.meta_scrape_max_delay_seconds
        )
        self._logger = logger.bind(component="meta_scraper_provider")

    async def close(self) -> None:
        """Close the underlying scrape session (HTTP client / browser)."""
        await self._session.close()

    async def search(self, request: AdSearchRequest) -> AdProviderResult:
        """Run one self-scrape search and return normalized advertisers + ads.

        Raises:
            AdLibraryProviderUnavailableError: when raw scraping is disabled by
                policy (``ad_library_allow_raw_scrape`` is false).
            LeadDiscoveryProviderError: hard transport / decoding failures.
            LeadDiscoveryRateLimitError: when the first page is throttled.
        """
        # Hard compliance gate — raises a mappable 503 unless explicitly enabled.
        ensure_self_scrape_allowed()

        # Gentle, scrape-specific hourly cap (far below the official tier) to
        # stay under the WAF radar, independent of the official-API budget.
        allowed, _used = await acquire_scrape_call_slot()
        if not allowed:
            raise LeadDiscoveryRateLimitError("Self-scrape hourly call cap reached")

        warnings: list[DiscoveryWarning] = []
        country = (request.country or "US").upper()

        page_id = request.page_id
        if page_id is None and request.page_name and not request.search_terms:
            page_id, resolve_warning = await self._resolve_page_id(request.page_name, country)
            if resolve_warning is not None:
                warnings.append(resolve_warning)

        raw_ads = await self._collect_ads(request, country, page_id, warnings)
        if not raw_ads:
            warnings.append(
                DiscoveryWarning(code="no_results", message="Self-scrape returned no ads.")
            )

        advertisers = group_advertisers(raw_ads, platform=self.platform, country=country)
        self._logger.info(
            "search_complete",
            country=country,
            raw_ad_count=len(raw_ads),
            advertiser_count=len(advertisers),
            has_page_filter=page_id is not None,
        )
        return AdProviderResult(
            platform=self.platform,
            advertisers=tuple(advertisers),
            requested_count=request.max_results,
            raw_ad_count=len(raw_ads),
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    async def _collect_ads(
        self,
        request: AdSearchRequest,
        country: str,
        page_id: str | None,
        warnings: list[DiscoveryWarning],
    ) -> list[dict[str, Any]]:
        # ``session_id`` + ``collation_token`` are client-generated once and held
        # constant across all pages of one search (they group the "collation");
        # only the GraphQL ``cursor`` advances per page.
        session_id = str(uuid.uuid4())
        collation_token = str(uuid.uuid4())
        cursor: str | None = None

        raw_ads: list[dict[str, Any]] = []
        # Bound pages so a runaway cursor can't exhaust the gentle hourly budget.
        max_pages = max(1, (request.max_results // _PAGE_SIZE) + 2)
        for page_index in range(max_pages):
            variables = self._build_search_variables(
                request,
                country,
                page_id,
                session_id=session_id,
                collation_token=collation_token,
                cursor=cursor,
            )
            try:
                envelope = await self._fetch_page(variables)
            except LeadDiscoveryRateLimitError:
                if not raw_ads:
                    raise
                warnings.append(
                    DiscoveryWarning(
                        code="rate_limited",
                        message="Self-scrape throttled mid-pagination; returning partial results.",
                    )
                )
                break

            connection = self._search_connection(envelope)
            edges = connection.get("edges")
            raw_ads.extend(flatten(edges if isinstance(edges, list) else []))
            if len(raw_ads) >= request.max_results:
                raw_ads = raw_ads[: request.max_results]
                break

            page_info = connection.get("page_info")
            page_info = page_info if isinstance(page_info, dict) else {}
            cursor = _str(page_info.get("end_cursor") or page_info.get("endCursor"))
            has_next = page_info.get("has_next_page", page_info.get("hasNextPage"))
            if not cursor or has_next is False:
                break
            # Gentle jittered pacing between pages to stay under the WAF radar.
            if page_index + 1 < max_pages:
                await self._sleep_jitter()
        return raw_ads

    @staticmethod
    def _search_connection(envelope: dict[str, Any]) -> dict[str, Any]:
        """Dig the GraphQL search connection (edges + page_info) out of the envelope."""
        data = envelope.get("data")
        data = data if isinstance(data, dict) else {}
        main = data.get("ad_library_main")
        main = main if isinstance(main, dict) else {}
        connection = main.get("search_results_connection")
        return connection if isinstance(connection, dict) else {}

    async def _fetch_page(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Fetch one search page, backing off once on a transient throttle."""
        doc_id = settings.meta_scrape_search_doc_id
        try:
            return await self._session.graphql(_SEARCH_FRIENDLY_NAME, doc_id, variables)
        except LeadDiscoveryRateLimitError:
            # One longer backoff, then retry; a second throttle propagates.
            await self._sleep(max(self._max_delay * 2, 1.0))
            return await self._session.graphql(_SEARCH_FRIENDLY_NAME, doc_id, variables)

    def _build_search_variables(
        self,
        request: AdSearchRequest,
        country: str,
        page_id: str | None,
        *,
        session_id: str,
        collation_token: str,
        cursor: str | None,
    ) -> dict[str, Any]:
        # Mirrors the ``variables`` blob the Ad Library website sends for
        # ``AdLibrarySearchPaginationQuery`` (captured from live traffic
        # 2026-06-12). Note the enum values are lowercase (``all`` /
        # ``keyword_unordered``) and several fields are JSON ``null``, not ``[]``.
        variables: dict[str, Any] = {
            "activeStatus": "all",
            "adType": "ALL",
            "bylines": [],
            "collationToken": collation_token,
            "contentLanguages": [],
            "countries": [country],
            "cursor": cursor or None,
            "excludedIDs": None,
            "first": _PAGE_SIZE,
            "isTargetedCountry": False,
            "location": None,
            "mediaType": "all",
            "multiCountryFilterMode": None,
            "pageIDs": [],
            "potentialReachInput": None,
            "publisherPlatforms": [],
            "queryString": request.search_terms or "",
            "regions": None,
            "searchType": "keyword_unordered",
            "sessionID": session_id,
            "sortData": None,
            "source": None,
            "startDate": None,
            "v": _SEARCH_VARIABLES_VERSION,
            "viewAllPageID": page_id or "0",
        }
        if page_id:
            variables["searchType"] = "page"
            variables["pageIDs"] = [page_id]
            variables["viewAllPageID"] = page_id
        return variables

    # ------------------------------------------------------------------
    # Page-name resolution
    # ------------------------------------------------------------------

    async def _resolve_page_id(
        self, page_name: str, country: str
    ) -> tuple[str | None, DiscoveryWarning | None]:
        """Resolve a page display name to its numeric id via the typeahead query."""
        variables = {
            "queryString": page_name,
            "isMobile": False,
            "country": country,
            "adType": "ALL",
        }
        try:
            envelope = await self._session.graphql(
                _TYPEAHEAD_FRIENDLY_NAME, settings.meta_scrape_typeahead_doc_id, variables
            )
        except LeadDiscoveryRateLimitError:
            return None, DiscoveryWarning(
                code="page_resolve_failed",
                message=f"Could not resolve page '{page_name}' (throttled).",
            )

        for entry in _typeahead_entries(envelope):
            pid = _str(entry.get("page_id") or entry.get("id"))
            if pid:
                return pid, None
        return None, DiscoveryWarning(
            code="page_not_found",
            message=f"No Ad Library page found for '{page_name}'.",
        )

    # ------------------------------------------------------------------
    # Pacing
    # ------------------------------------------------------------------

    async def _sleep_jitter(self) -> None:
        low = max(0.0, self._min_delay)
        high = max(low, self._max_delay)
        await self._sleep(random.uniform(low, high))

    @staticmethod
    async def _sleep(seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)


def _typeahead_entries(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the page-result entries out of the typeahead GraphQL envelope.

    Tolerates the couple of nesting shapes Meta has used for the typeahead
    suggestions (``ad_library_page_typeahead`` vs nested under
    ``ad_library_main``).
    """
    data = envelope.get("data")
    data = data if isinstance(data, dict) else {}
    containers: list[Any] = [
        data.get("ad_library_page_typeahead"),
        _dig(data, "ad_library_main", "typeahead_suggestions"),
        data.get("ad_library_main"),
    ]
    for container in containers:
        if not isinstance(container, dict):
            continue
        entries = container.get("page_results") or container.get("pageResults")
        if isinstance(entries, list):
            return [e for e in entries if isinstance(e, dict)]
    return []


def _dig(obj: Any, *keys: str) -> Any:
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
