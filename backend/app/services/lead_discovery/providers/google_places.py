"""Google Places lead-discovery provider.

Thin adapter around :class:`app.services.scraping.google_places.GooglePlacesService`
that turns its dict-shaped payloads into normalized :class:`RawLead` objects.

The existing Find Leads endpoint (``app/api/v1/find_leads_ai.py``) keeps using
the underlying ``GooglePlacesService`` directly — this provider exists for the
source-agnostic lead miner, so swapping in a new provider does not touch the
Google Places search endpoint.
"""

from __future__ import annotations

from typing import Any, ClassVar

import structlog

from app.services.lead_discovery.dedupe import dedupe_raw_leads, extract_host
from app.services.lead_discovery.errors import (
    LeadDiscoveryAuthError,
    LeadDiscoveryProviderError,
    LeadDiscoveryRateLimitError,
)
from app.services.lead_discovery.protocol import BaseLeadDiscoveryProvider
from app.services.lead_discovery.types import (
    DiscoveryWarning,
    LeadDiscoveryRequest,
    ProviderResult,
    RawLead,
)
from app.services.scraping.google_places import (
    GooglePlacesAuthError,
    GooglePlacesError,
    GooglePlacesRateLimitError,
    GooglePlacesService,
)

logger = structlog.get_logger()

SOURCE_TYPE = "google_places"


class GooglePlacesLeadProvider(BaseLeadDiscoveryProvider):
    """Wrap ``GooglePlacesService`` behind the lead-discovery protocol."""

    source_type: ClassVar[str] = SOURCE_TYPE

    def __init__(self, service: GooglePlacesService | None = None) -> None:
        """Initialize the provider.

        Args:
            service: Optional pre-built ``GooglePlacesService`` (for tests
                and dependency injection). When omitted the provider builds
                its own instance and owns its lifecycle.
        """
        self._service = service or GooglePlacesService()
        # Only close the inner service if the caller didn't hand one in —
        # respect ownership so shared services aren't torn down twice.
        self._owns_service = service is None
        self._logger = logger.bind(component="google_places_lead_provider")

    async def search(self, request: LeadDiscoveryRequest) -> ProviderResult:
        """Run a Google Places text search and return normalized leads.

        Raises:
            LeadDiscoveryAuthError: ``GooglePlacesAuthError`` from the API.
            LeadDiscoveryRateLimitError: ``GooglePlacesRateLimitError``.
            LeadDiscoveryProviderError: any other ``GooglePlacesError``.
        """
        warnings: list[DiscoveryWarning] = []

        # Empty queries are a soft failure — the lead miner may pass an
        # under-specified request; surface a warning and return empty.
        query = (request.query or "").strip()
        if not query:
            warnings.append(
                DiscoveryWarning(
                    code="empty_query",
                    message="Google Places requires a non-empty text query.",
                )
            )
            return ProviderResult(
                source_type=self.source_type,
                leads=(),
                requested_count=request.max_results,
                raw_count=0,
                duplicate_count=0,
                warnings=tuple(warnings),
            )

        log = self._logger.bind(
            operation="search",
            query=query,
            max_results=request.max_results,
        )

        try:
            raw_payloads = await self._service.search_businesses(
                query=query,
                max_results=request.max_results,
            )
        except GooglePlacesAuthError as exc:
            log.warning("auth_error", error=str(exc))
            raise LeadDiscoveryAuthError(str(exc)) from exc
        except GooglePlacesRateLimitError as exc:
            log.warning("rate_limited", error=str(exc))
            raise LeadDiscoveryRateLimitError(str(exc)) from exc
        except GooglePlacesError as exc:
            log.warning("provider_error", error=str(exc))
            raise LeadDiscoveryProviderError(str(exc)) from exc

        leads = [self._payload_to_raw_lead(payload, request) for payload in raw_payloads]
        unique_leads, duplicate_count = dedupe_raw_leads(leads)

        log.info(
            "search_complete",
            raw_count=len(raw_payloads),
            unique_count=len(unique_leads),
            duplicate_count=duplicate_count,
        )

        return ProviderResult(
            source_type=self.source_type,
            leads=unique_leads,
            requested_count=request.max_results,
            raw_count=len(raw_payloads),
            duplicate_count=duplicate_count,
            warnings=tuple(warnings),
        )

    async def close(self) -> None:
        """Close the underlying HTTP client when we own the service."""
        if self._owns_service:
            await self._service.close()

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @classmethod
    def _payload_to_raw_lead(
        cls,
        payload: dict[str, Any],
        request: LeadDiscoveryRequest,
    ) -> RawLead:
        """Map one ``GooglePlacesService.search_businesses`` dict to a RawLead.

        ``GooglePlacesService._transform_place`` already does the bulk of the
        translation (``displayName.text`` → ``name`` etc.); this layer adds
        the source-type tag, host extraction, and a verbatim copy of the
        provider extras so the audit row keeps everything Google returned.
        """
        place_id = _str_or_none(payload.get("place_id"))
        name = _str_or_none(payload.get("name"))
        address = _str_or_none(payload.get("address"))
        phone_number = _str_or_none(payload.get("phone_number"))
        website = _str_or_none(payload.get("website"))
        website_host = extract_host(website)

        rating_raw = payload.get("rating")
        rating: float | None = float(rating_raw) if isinstance(rating_raw, int | float) else None

        review_count_raw = payload.get("review_count", 0)
        review_count: int = (
            int(review_count_raw) if isinstance(review_count_raw, int | float) else 0
        )

        types_raw = payload.get("types") or ()
        types: tuple[str, ...] = (
            tuple(str(t) for t in types_raw if t) if isinstance(types_raw, list | tuple) else ()
        )

        source_metadata: dict[str, Any] = {
            "business_status": payload.get("business_status"),
            "has_phone": bool(payload.get("has_phone")),
            "has_website": bool(payload.get("has_website")),
            "raw_types": list(types),
        }
        if request.query:
            source_metadata["source_query"] = request.query

        return RawLead(
            source_type=SOURCE_TYPE,
            source_external_id=place_id,
            name=name,
            phone_number=phone_number,
            email=None,
            website=website,
            website_host=website_host,
            address=address,
            country_code=request.country_code,
            region=request.region,
            city=request.city,
            location_label=request.location_label,
            rating=rating,
            review_count=review_count,
            types=types,
            source_metadata=source_metadata,
        )


def _str_or_none(value: object) -> str | None:
    """Return ``value`` as a non-empty string, or ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
