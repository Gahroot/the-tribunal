"""Execute a ``web_people`` discovery job into ``lead_prospects``.

Mirrors :func:`app.services.ad_intelligence.discovery.run_discovery_job` for the
people-extraction source: build the provider from the job, crawl, then upsert
one :class:`LeadProspect` per discovered person through the shared person
dedupe facet so re-runs merge instead of duplicating. The function mutates the
job (counters, status, timing) and flushes, but commits nothing — the worker
owns the transaction boundary.

Guessed emails are persisted but stamped ``email_status="unverified"`` in
provenance; the enrichment worker verifies them later.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import hash_value
from app.models.lead_discovery_job import DiscoveryJobStatus, LeadDiscoveryJob
from app.models.lead_prospect import (
    LeadProspect,
    ProspectIdentityKind,
    ProspectStatus,
)
from app.services.lead_discovery.dedupe import dedupe_key_for_person
from app.services.lead_discovery.providers.web_people import WebPeopleLeadProvider
from app.services.lead_discovery.types import LeadDiscoveryRequest, RawLead

logger = structlog.get_logger()


@dataclass(slots=True)
class PeopleDiscoveryOutcome:
    """Result of running one ``web_people`` discovery job."""

    discovered_count: int
    duplicate_count: int
    warnings: list[str]


def request_from_job(job: LeadDiscoveryJob) -> LeadDiscoveryRequest:
    """Build a :class:`LeadDiscoveryRequest` from a discovery job's params."""
    params = dict(job.params or {})
    max_results = int(params.get("max_results") or job.requested_count or 25)
    return LeadDiscoveryRequest(
        query=job.query,
        max_results=max_results,
        location_label=params.get("location_label"),
        country_code=params.get("country_code"),
        region=params.get("region"),
        city=params.get("city"),
        params=params,
    )


async def run_people_discovery_job(
    db: AsyncSession,
    job: LeadDiscoveryJob,
    *,
    provider: WebPeopleLeadProvider | None = None,
) -> PeopleDiscoveryOutcome:
    """Crawl + persist people for ``job``. Mutates the job; does not commit."""
    log = logger.bind(
        component="people_discovery",
        job_id=str(job.id),
        workspace_id=str(job.workspace_id),
    )
    job.status = DiscoveryJobStatus.RUNNING
    job.started_at = job.started_at or datetime.now(UTC)

    request = request_from_job(job)
    owns_provider = provider is None
    active_provider = provider or WebPeopleLeadProvider()
    try:
        result = await active_provider.search(request)
    finally:
        if owns_provider:
            await active_provider.close()

    discovered = 0
    duplicates = 0
    for lead in result.leads:
        created = await _upsert_person_prospect(db, job, lead)
        if created:
            discovered += 1
        else:
            duplicates += 1
    await db.flush()

    warnings = [w.message for w in result.warnings]
    job.discovered_count = discovered
    job.duplicate_count = duplicates + result.duplicate_count
    job.status = DiscoveryJobStatus.SUCCEEDED
    job.completed_at = datetime.now(UTC)
    if warnings:
        job.last_error = "; ".join(warnings)[:2000]

    log.info(
        "people_discovery_complete",
        discovered=discovered,
        duplicates=duplicates,
        warnings=len(warnings),
    )
    return PeopleDiscoveryOutcome(
        discovered_count=discovered,
        duplicate_count=duplicates + result.duplicate_count,
        warnings=warnings,
    )


async def _upsert_person_prospect(
    db: AsyncSession,
    job: LeadDiscoveryJob,
    lead: RawLead,
) -> bool:
    """Insert or merge a person prospect for ``lead``. Returns True if created."""
    dedupe_key = dedupe_key_for_person(
        email=lead.email,
        full_name=lead.full_name,
        first_name=lead.first_name,
        last_name=lead.last_name,
        website=lead.website,
        website_host=lead.website_host,
    )

    existing: LeadProspect | None = None
    if dedupe_key is not None:
        found = await db.execute(
            select(LeadProspect).where(
                LeadProspect.workspace_id == job.workspace_id,
                LeadProspect.dedupe_key == dedupe_key,
            )
        )
        existing = found.scalar_one_or_none()

    confidence = int(lead.source_metadata.get("confidence") or 0)
    email_unverified = bool(lead.source_metadata.get("email_unverified"))
    provenance: dict[str, Any] = {
        "source": "web_people",
        "source_page": lead.source_metadata.get("source_page"),
        "extraction_confidence": confidence,
        "email_status": "unverified" if email_unverified else "none",
        "email_pattern": lead.source_metadata.get("email_pattern"),
        "discovery_job_id": str(job.id),
    }
    evidence = [
        {
            "type": "person_extraction",
            "source": "web_people",
            "title": lead.title,
            "confidence": confidence,
            "source_page": lead.source_metadata.get("source_page"),
        }
    ]

    if existing is not None:
        _merge_person(existing, lead, provenance, evidence, job.mission_id)
        return False

    db.add(
        LeadProspect(
            workspace_id=job.workspace_id,
            mission_id=job.mission_id,
            discovery_job_id=job.id,
            identity_kind=(
                ProspectIdentityKind.EMAIL if lead.email else ProspectIdentityKind.OWNER_NAME
            ),
            first_name=lead.first_name,
            last_name=lead.last_name,
            full_name=lead.full_name,
            title=lead.title,
            email=lead.email,
            email_hash=hash_value(lead.email) if lead.email else None,
            company_name=lead.name if lead.name != lead.full_name else None,
            website_url=lead.website,
            website_host=lead.website_host,
            website_host_hash=hash_value(lead.website_host) if lead.website_host else None,
            owner_name_hash=hash_value(lead.full_name.lower()) if lead.full_name else None,
            country_code=lead.country_code,
            region=lead.region,
            city=lead.city,
            location_label=lead.location_label,
            source_type=lead.source_type,
            source_external_id=lead.source_external_id,
            source_query=job.query,
            dedupe_key=dedupe_key,
            provenance=provenance,
            evidence=evidence,
            lead_score=confidence,
            status=ProspectStatus.NEW,
        )
    )
    return True


def _merge_person(
    prospect: LeadProspect,
    lead: RawLead,
    provenance: dict[str, Any],
    evidence: list[dict[str, Any]],
    mission_id: uuid.UUID | None,
) -> None:
    """Fill gaps on an existing prospect from a freshly extracted person."""
    if not prospect.full_name and lead.full_name:
        prospect.full_name = lead.full_name
    if not prospect.first_name and lead.first_name:
        prospect.first_name = lead.first_name
    if not prospect.last_name and lead.last_name:
        prospect.last_name = lead.last_name
    if not prospect.title and lead.title:
        prospect.title = lead.title
    if not prospect.email_hash and lead.email:
        prospect.email = lead.email
        prospect.email_hash = hash_value(lead.email)
    prospect.evidence = [*(prospect.evidence or []), *evidence]
    merged = dict(prospect.provenance or {})
    merged.setdefault("web_people", provenance)
    prospect.provenance = merged
    if mission_id and prospect.mission_id is None:
        prospect.mission_id = mission_id
