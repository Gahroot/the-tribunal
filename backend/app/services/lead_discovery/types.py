"""Shared value types for source-agnostic lead discovery.

These are the normalized request/response objects that providers speak to the
lead miner. They are deliberately decoupled from
``app.schemas.scraping.BusinessResult`` (Google Places shape) and from the
``LeadProspect`` ORM model so we can introduce new sources without touching
either layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class LeadDiscoveryRequest:
    """A single lead-discovery query against one provider.

    Attributes:
        query: Free-text search term ("plumbers in Austin TX"). Optional for
            providers that only accept structured params (e.g. CSV uploads,
            LinkedIn audience filters).
        max_results: Soft cap on the number of normalized leads the provider
            should return. Providers may return fewer.
        location_label: Optional human-readable location label
            ("Austin, TX") for providers that prefer a structured locale.
        country_code: Optional ISO-3166-1 alpha-2 hint ("US").
        region: Optional region/state label ("TX").
        city: Optional city label ("Austin").
        params: Provider-specific extra parameters. Keep this small and
            documented per provider.
    """

    query: str | None = None
    max_results: int = 20
    location_label: str | None = None
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class RawLead:
    """One normalized lead candidate emitted by a discovery provider.

    Every provider maps its native payload into this shape; downstream code
    (lead miner, dedupe, enrichment, prospect persistence) only depends on
    these fields. Anything provider-specific lives in ``source_metadata``.

    Attributes:
        source_type: Discovery-source identifier (matches
            ``DiscoverySourceType`` values; stored as plain string so new
            providers don't require an enum migration).
        source_external_id: Stable provider-side identifier when available
            (e.g. Google Places ``place_id``). Used for cross-run dedupe.
        name: Display / company name.
        phone_number: Best-effort phone number (provider-formatted; the
            discovery pipeline normalizes to E.164 downstream).
        email: Best-effort email address.
        website: Public website URL when known.
        website_host: Lowercase host portion of ``website`` when extractable.
        address: Formatted postal address line.
        country_code, region, city, location_label: Structured location bits.
        rating: Provider rating, when applicable (Google Places 1-5).
        review_count: Provider review count.
        types: Business categories/tags the provider attached.
        first_name, last_name, full_name, title: Owner/contact identity bits.
        linkedin_url: LinkedIn profile/company URL when known.
        source_metadata: Raw provider extras kept verbatim for audit /
            forensic / fallback use.
    """

    source_type: str
    name: str | None = None
    source_external_id: str | None = None
    phone_number: str | None = None
    email: str | None = None
    website: str | None = None
    website_host: str | None = None
    address: str | None = None
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    location_label: str | None = None
    rating: float | None = None
    review_count: int = 0
    types: tuple[str, ...] = ()
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    title: str | None = None
    linkedin_url: str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_phone(self) -> bool:
        return bool(self.phone_number)

    @property
    def has_email(self) -> bool:
        return bool(self.email)

    @property
    def has_website(self) -> bool:
        return bool(self.website or self.website_host)

    @property
    def has_owner_name(self) -> bool:
        return bool(self.full_name or self.first_name or self.last_name)


@dataclass(slots=True, frozen=True)
class DiscoveryWarning:
    """A soft, non-fatal problem reported by a provider during discovery.

    Use for partial-page failures, throttling, skipped result rows — anything
    the discovery job should record but that does not invalidate the rest of
    the batch. Hard failures should raise
    ``LeadDiscoveryProviderError`` instead.
    """

    code: str
    message: str
    detail: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class ProviderResult:
    """Outcome of a single ``LeadDiscoveryProvider.search`` call.

    Attributes:
        source_type: Identifier of the provider that produced this result.
        leads: Deduplicated normalized leads. Empty tuple is valid (no
            matches). Order matches the provider's ranking.
        requested_count: ``max_results`` from the originating request.
        raw_count: Number of candidates the upstream API returned, before
            within-batch dedupe.
        duplicate_count: Number of within-batch duplicates removed.
        warnings: Soft, non-fatal warnings emitted during the run.
    """

    source_type: str
    leads: tuple[RawLead, ...]
    requested_count: int
    raw_count: int = 0
    duplicate_count: int = 0
    warnings: tuple[DiscoveryWarning, ...] = ()

    @property
    def lead_count(self) -> int:
        return len(self.leads)
