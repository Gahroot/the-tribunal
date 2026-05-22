"""Tests for the value types in ``app.services.lead_discovery.types``.

These pin the public contract of ``LeadDiscoveryRequest``, ``RawLead``,
``DiscoveryWarning``, and ``ProviderResult`` so the lead miner can rely on
defaults and identity helpers without re-checking the dataclass each call.
"""

from __future__ import annotations

import pytest

from app.services.lead_discovery.types import (
    DiscoveryWarning,
    LeadDiscoveryRequest,
    ProviderResult,
    RawLead,
)


class TestLeadDiscoveryRequest:
    def test_defaults(self) -> None:
        req = LeadDiscoveryRequest()
        assert req.query is None
        assert req.max_results == 20
        assert req.location_label is None
        assert req.country_code is None
        assert req.region is None
        assert req.city is None
        assert req.params == {}

    def test_frozen_rejects_attr_set(self) -> None:
        req = LeadDiscoveryRequest(query="x")
        with pytest.raises((AttributeError, TypeError)):
            req.query = "y"  # type: ignore[misc]


class TestRawLeadIdentityHelpers:
    def test_has_phone_true_when_phone_set(self) -> None:
        lead = RawLead(source_type="t", phone_number="+15551234567")
        assert lead.has_phone is True
        assert lead.has_email is False
        assert lead.has_website is False
        assert lead.has_owner_name is False

    def test_has_email_true_when_email_set(self) -> None:
        lead = RawLead(source_type="t", email="a@b.com")
        assert lead.has_email is True

    def test_has_website_true_for_url_or_host(self) -> None:
        assert RawLead(source_type="t", website="https://x.example").has_website is True
        assert RawLead(source_type="t", website_host="x.example").has_website is True
        assert RawLead(source_type="t").has_website is False

    def test_has_owner_name_true_for_any_name_field(self) -> None:
        assert RawLead(source_type="t", full_name="John").has_owner_name is True
        assert RawLead(source_type="t", first_name="John").has_owner_name is True
        assert RawLead(source_type="t", last_name="Doe").has_owner_name is True
        assert RawLead(source_type="t").has_owner_name is False

    def test_types_tuple_default(self) -> None:
        lead = RawLead(source_type="t")
        assert lead.types == ()
        # Tuples are hashable / immutable, unlike list defaults.
        assert isinstance(lead.types, tuple)

    def test_frozen_rejects_attr_set(self) -> None:
        lead = RawLead(source_type="t")
        with pytest.raises((AttributeError, TypeError)):
            lead.name = "x"  # type: ignore[misc]


class TestDiscoveryWarning:
    def test_required_fields(self) -> None:
        warn = DiscoveryWarning(code="x", message="y")
        assert warn.code == "x"
        assert warn.message == "y"
        assert warn.detail is None

    def test_detail_payload_kept(self) -> None:
        warn = DiscoveryWarning(code="x", message="y", detail={"k": 1})
        assert warn.detail == {"k": 1}


class TestProviderResult:
    def test_lead_count_matches_leads(self) -> None:
        leads = (
            RawLead(source_type="t", phone_number="+15551234567"),
            RawLead(source_type="t", email="a@b.com"),
        )
        result = ProviderResult(
            source_type="t",
            leads=leads,
            requested_count=10,
            raw_count=2,
            duplicate_count=0,
        )
        assert result.lead_count == 2
        assert result.warnings == ()

    def test_warnings_round_trip(self) -> None:
        warn = DiscoveryWarning(code="x", message="y")
        result = ProviderResult(
            source_type="t",
            leads=(),
            requested_count=0,
            warnings=(warn,),
        )
        assert result.warnings == (warn,)
        assert result.lead_count == 0
