"""Tests for the Google Places lead-discovery provider.

These cover the normalization layer (``GooglePlacesService`` dict →
``RawLead``), the within-batch dedupe wiring, the empty-query soft failure,
and the error-class mapping from ``GooglePlacesError`` sub-types to
``LeadDiscoveryProviderError`` sub-types.

``GooglePlacesService.search_businesses`` is patched at the instance level so
no real HTTP traffic ever leaves the test runner.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services.lead_discovery import (
    DiscoveryWarning,
    GooglePlacesLeadProvider,
    LeadDiscoveryAuthError,
    LeadDiscoveryProvider,
    LeadDiscoveryProviderError,
    LeadDiscoveryRateLimitError,
    LeadDiscoveryRequest,
    ProviderResult,
    RawLead,
)
from app.services.lead_discovery.dedupe import dedupe_key_for_phone
from app.services.scraping.google_places import (
    GooglePlacesAuthError,
    GooglePlacesError,
    GooglePlacesRateLimitError,
    GooglePlacesService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_payload(
    *,
    place_id: str = "ChIJ_test_1",
    name: str = "Acme Plumbing",
    address: str = "123 Main St, Austin, TX 78701, USA",
    phone_number: str | None = "+1 512-555-0100",
    website: str | None = "https://www.acmeplumbing.example/",
    rating: float | None = 4.6,
    review_count: int = 128,
    types: list[str] | None = None,
    business_status: str = "OPERATIONAL",
) -> dict[str, Any]:
    """Build a payload shaped like ``GooglePlacesService._transform_place``."""
    if types is None:
        types = ["plumber", "point_of_interest"]
    return {
        "place_id": place_id,
        "name": name,
        "address": address,
        "phone_number": phone_number,
        "website": website,
        "rating": rating,
        "review_count": review_count,
        "types": types,
        "business_status": business_status,
        "has_phone": bool(phone_number),
        "has_website": bool(website),
    }


def _make_provider_with_payloads(payloads: list[dict[str, Any]]) -> GooglePlacesLeadProvider:
    """Wire a provider whose ``search_businesses`` returns ``payloads``."""
    service = GooglePlacesService(api_key="test-key")
    service.search_businesses = AsyncMock(return_value=payloads)  # type: ignore[method-assign]
    service.close = AsyncMock()  # type: ignore[method-assign]
    return GooglePlacesLeadProvider(service=service)


def _make_provider_raising(exc: Exception) -> GooglePlacesLeadProvider:
    """Wire a provider whose ``search_businesses`` raises ``exc``."""
    service = GooglePlacesService(api_key="test-key")
    service.search_businesses = AsyncMock(side_effect=exc)  # type: ignore[method-assign]
    service.close = AsyncMock()  # type: ignore[method-assign]
    return GooglePlacesLeadProvider(service=service)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_implements_lead_discovery_provider_protocol(self) -> None:
        provider = GooglePlacesLeadProvider(service=GooglePlacesService(api_key="x"))
        assert isinstance(provider, LeadDiscoveryProvider)
        assert provider.source_type == "google_places"


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


class TestNormalization:
    async def test_payload_maps_every_field(self) -> None:
        provider = _make_provider_with_payloads([_make_payload()])
        result = await provider.search(
            LeadDiscoveryRequest(
                query="plumbers in Austin TX",
                max_results=10,
                location_label="Austin, TX",
                country_code="US",
                region="TX",
                city="Austin",
            )
        )
        assert isinstance(result, ProviderResult)
        assert result.source_type == "google_places"
        assert result.lead_count == 1

        lead = result.leads[0]
        assert isinstance(lead, RawLead)
        assert lead.source_type == "google_places"
        assert lead.source_external_id == "ChIJ_test_1"
        assert lead.name == "Acme Plumbing"
        assert lead.address == "123 Main St, Austin, TX 78701, USA"
        assert lead.phone_number == "+1 512-555-0100"
        assert lead.website == "https://www.acmeplumbing.example/"
        # Host extraction strips scheme + ``www.`` and lowercases.
        assert lead.website_host == "acmeplumbing.example"
        assert lead.rating == pytest.approx(4.6)
        assert lead.review_count == 128
        assert lead.types == ("plumber", "point_of_interest")
        # Location bits propagate from the request, not the payload.
        assert lead.country_code == "US"
        assert lead.region == "TX"
        assert lead.city == "Austin"
        assert lead.location_label == "Austin, TX"
        # Google extras are preserved on source_metadata for forensic use.
        assert lead.source_metadata["business_status"] == "OPERATIONAL"
        assert lead.source_metadata["has_phone"] is True
        assert lead.source_metadata["has_website"] is True
        assert lead.source_metadata["raw_types"] == ["plumber", "point_of_interest"]
        assert lead.source_metadata["source_query"] == "plumbers in Austin TX"

    async def test_missing_optional_fields_become_none(self) -> None:
        payload = _make_payload(
            phone_number=None,
            website=None,
            rating=None,
            review_count=0,
            types=[],
        )
        provider = _make_provider_with_payloads([payload])
        result = await provider.search(LeadDiscoveryRequest(query="dentists"))
        assert result.lead_count == 1
        lead = result.leads[0]
        assert lead.phone_number is None
        assert lead.website is None
        assert lead.website_host is None
        assert lead.rating is None
        assert lead.review_count == 0
        assert lead.types == ()

    async def test_empty_strings_become_none(self) -> None:
        payload = _make_payload(phone_number=" ", website="")
        # Override two payload fields directly — _make_payload normalizes
        # ``None`` differently than empty strings.
        payload["address"] = ""
        provider = _make_provider_with_payloads([payload])
        result = await provider.search(LeadDiscoveryRequest(query="x"))
        lead = result.leads[0]
        assert lead.phone_number is None
        assert lead.website is None
        assert lead.address is None

    async def test_int_rating_coerced_to_float(self) -> None:
        # Some payloads carry an integer rating like 5; keep typing strict.
        payload = _make_payload(rating=5)
        provider = _make_provider_with_payloads([payload])
        result = await provider.search(LeadDiscoveryRequest(query="x"))
        lead = result.leads[0]
        assert isinstance(lead.rating, float)
        assert lead.rating == pytest.approx(5.0)

    async def test_unexpected_types_field_shape_defaults_empty(self) -> None:
        payload = _make_payload()
        payload["types"] = "not-a-list"  # malformed upstream response
        provider = _make_provider_with_payloads([payload])
        result = await provider.search(LeadDiscoveryRequest(query="x"))
        lead = result.leads[0]
        assert lead.types == ()
        # raw_types still echoes what the lead carries.
        assert lead.source_metadata["raw_types"] == []


# ---------------------------------------------------------------------------
# Within-batch dedupe
# ---------------------------------------------------------------------------


class TestDedupeWiring:
    async def test_duplicate_phone_collapsed(self) -> None:
        payloads = [
            _make_payload(place_id="A", name="A", phone_number="+12025550100"),
            _make_payload(place_id="B", name="B", phone_number="(202) 555-0100"),
            _make_payload(place_id="C", name="C", phone_number="+12025550200"),
        ]
        provider = _make_provider_with_payloads(payloads)
        result = await provider.search(LeadDiscoveryRequest(query="x", max_results=10))

        assert result.raw_count == 3
        assert result.lead_count == 2
        assert result.duplicate_count == 1
        # Earliest occurrence wins.
        assert [lead.name for lead in result.leads] == ["A", "C"]

    async def test_first_lead_carries_dedupe_compatible_phone(self) -> None:
        payloads = [_make_payload(phone_number="(202) 555-0100")]
        provider = _make_provider_with_payloads(payloads)
        result = await provider.search(LeadDiscoveryRequest(query="x"))
        # Phone passes through unchanged; dedupe re-normalizes it.
        assert result.leads[0].phone_number == "(202) 555-0100"
        assert dedupe_key_for_phone(result.leads[0].phone_number) is not None


# ---------------------------------------------------------------------------
# Empty / soft-failure surface
# ---------------------------------------------------------------------------


class TestEmptyAndSoftFailures:
    async def test_no_upstream_results_returns_empty_result(self) -> None:
        provider = _make_provider_with_payloads([])
        result = await provider.search(LeadDiscoveryRequest(query="nobody here"))
        assert result.leads == ()
        assert result.lead_count == 0
        assert result.raw_count == 0
        assert result.duplicate_count == 0
        assert result.warnings == ()

    async def test_empty_query_returns_warning_without_calling_upstream(self) -> None:
        service = GooglePlacesService(api_key="x")
        service.search_businesses = AsyncMock()  # type: ignore[method-assign]
        provider = GooglePlacesLeadProvider(service=service)

        result = await provider.search(LeadDiscoveryRequest(query="   ", max_results=5))

        assert result.leads == ()
        assert result.warnings
        assert isinstance(result.warnings[0], DiscoveryWarning)
        assert result.warnings[0].code == "empty_query"
        # Upstream must not be touched on a soft-failed request.
        service.search_businesses.assert_not_called()

    async def test_none_query_treated_as_empty_query(self) -> None:
        service = GooglePlacesService(api_key="x")
        service.search_businesses = AsyncMock()  # type: ignore[method-assign]
        provider = GooglePlacesLeadProvider(service=service)
        result = await provider.search(LeadDiscoveryRequest(query=None))
        assert result.warnings[0].code == "empty_query"
        service.search_businesses.assert_not_called()


# ---------------------------------------------------------------------------
# Error class mapping
# ---------------------------------------------------------------------------


class TestErrorMapping:
    async def test_auth_error_wrapped(self) -> None:
        provider = _make_provider_raising(GooglePlacesAuthError("bad key"))
        with pytest.raises(LeadDiscoveryAuthError) as exc_info:
            await provider.search(LeadDiscoveryRequest(query="x"))
        # Sub-class hierarchy preserved.
        assert isinstance(exc_info.value, LeadDiscoveryProviderError)
        assert "bad key" in str(exc_info.value)

    async def test_rate_limit_error_wrapped(self) -> None:
        provider = _make_provider_raising(GooglePlacesRateLimitError("429"))
        with pytest.raises(LeadDiscoveryRateLimitError) as exc_info:
            await provider.search(LeadDiscoveryRequest(query="x"))
        assert isinstance(exc_info.value, LeadDiscoveryProviderError)

    async def test_other_provider_error_wrapped_as_base(self) -> None:
        provider = _make_provider_raising(GooglePlacesError("server fire"))
        with pytest.raises(LeadDiscoveryProviderError) as exc_info:
            await provider.search(LeadDiscoveryRequest(query="x"))
        # Must NOT escalate a generic error to the auth/ratelimit subclass.
        assert not isinstance(exc_info.value, LeadDiscoveryAuthError)
        assert not isinstance(exc_info.value, LeadDiscoveryRateLimitError)


# ---------------------------------------------------------------------------
# Lifecycle / ownership
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_close_closes_owned_service(self) -> None:
        provider = GooglePlacesLeadProvider()
        # Replace the auto-built service so we don't open a real HTTP client.
        replacement = GooglePlacesService(api_key="x")
        replacement.close = AsyncMock()  # type: ignore[method-assign]
        provider._service = replacement
        # Force-own the replacement.
        provider._owns_service = True

        await provider.close()
        replacement.close.assert_awaited_once()

    async def test_close_skips_injected_service(self) -> None:
        injected = GooglePlacesService(api_key="x")
        injected.close = AsyncMock()  # type: ignore[method-assign]
        provider = GooglePlacesLeadProvider(service=injected)

        await provider.close()
        injected.close.assert_not_called()
