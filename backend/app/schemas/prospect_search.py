"""Pydantic schemas for Apollo-style people search + buying signals.

These back the workspace-scoped ``/prospects`` router: cross-mission people
search with signal filters, on-demand email reveal, launching a ``web_people``
discovery job, and bulk add-to-mission.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.lead_prospect import ProspectStatus
from app.models.prospect_signal import ProspectSignalStatus

# --- Signals --------------------------------------------------------------


class ProspectSignalResponse(BaseModel):
    """One normalized buying signal attached to a prospect."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    signal_type: str
    strength: int
    status: ProspectSignalStatus
    source: str | None
    payload: dict[str, Any]
    observed_at: datetime


# --- People search --------------------------------------------------------


class PeopleSearchRequest(BaseModel):
    """Filters for a cross-mission people search, ranked by score."""

    # Free-text matched against name/title/company.
    keywords: str | None = Field(default=None, max_length=200)
    # Title / seniority filters (case-insensitive substring match, any-of).
    title: str | None = Field(default=None, max_length=200)
    seniority: list[str] = Field(default_factory=list)
    # Location / firmographics.
    location: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=200)
    country_code: str | None = Field(default=None, max_length=2)
    # Channel presence.
    has_email: bool | None = None
    has_phone: bool | None = None
    # Signal filters: prospect must carry at least one signal of these types.
    signal_types: list[str] = Field(default_factory=list)
    min_signal_strength: int = Field(default=0, ge=0, le=100)
    # Scoring + status.
    min_score: int = Field(default=0, ge=0)
    statuses: list[ProspectStatus] = Field(default_factory=list)
    mission_id: uuid.UUID | None = None
    # Pagination.
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)


class PersonResult(BaseModel):
    """One person row in a people-search result, with attached signals."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    mission_id: uuid.UUID | None
    contact_id: int | None

    first_name: str | None
    last_name: str | None
    full_name: str | None
    title: str | None

    email: str | None
    phone_number: str | None
    has_email: bool
    has_phone: bool

    company_name: str | None
    website_url: str | None
    website_host: str | None
    linkedin_url: str | None

    country_code: str | None
    region: str | None
    city: str | None
    location_label: str | None

    source_type: str | None
    lead_score: int
    status: ProspectStatus
    provenance: dict[str, Any]

    discovered_at: datetime
    signals: list[ProspectSignalResponse] = Field(default_factory=list)


class PeopleSearchResponse(BaseModel):
    """Paginated people-search result."""

    items: list[PersonResult]
    total: int
    page: int
    page_size: int
    pages: int


# --- Reveal email ---------------------------------------------------------


class RevealEmailResponse(BaseModel):
    """Outcome of an on-demand email reveal + verification."""

    prospect_id: uuid.UUID
    email: str | None
    pattern: str | None
    verification_status: str
    confidence: int
    candidates: list[dict[str, Any]] = Field(default_factory=list)


# --- Reveal phone ---------------------------------------------------------


class RevealPhoneResponse(BaseModel):
    """Outcome of an on-demand phone reveal.

    Returns a best-effort **business / main line** scraped from the company's
    own website — not a personal direct dial. ``candidates`` holds the ranked
    alternatives to try.
    """

    prospect_id: uuid.UUID
    phone_number: str | None
    source: str | None
    candidates: list[dict[str, Any]] = Field(default_factory=list)


# --- People discovery -----------------------------------------------------


class PeopleDiscoveryRequest(BaseModel):
    """Launch a ``web_people`` discovery job.

    Provide either ``domain``/``domains`` (crawl those company sites directly)
    or a ``query`` (resolve companies via Google Places, then crawl each).
    """

    query: str | None = Field(default=None, max_length=300)
    domain: str | None = Field(default=None, max_length=255)
    domains: list[str] = Field(default_factory=list)
    mission_id: uuid.UUID | None = None
    max_results: int = Field(default=25, ge=1, le=200)
    location_label: str | None = Field(default=None, max_length=255)
    country_code: str | None = Field(default=None, max_length=2)
    region: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)


class PeopleDiscoveryResponse(BaseModel):
    """Response for a launched ``web_people`` discovery job."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    mission_id: uuid.UUID | None
    source_type: str
    status: str
    query: str | None
    requested_count: int
    created_at: datetime


# --- Add to mission -------------------------------------------------------


class AddToMissionRequest(BaseModel):
    """Attach selected prospects to an outbound mission."""

    mission_id: uuid.UUID
    prospect_ids: list[uuid.UUID] = Field(default_factory=list, min_length=1, max_length=500)


class AddToMissionResponse(BaseModel):
    """Outcome of a bulk add-to-mission operation."""

    mission_id: uuid.UUID
    added: int
    skipped: int
