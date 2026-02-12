"""Find Leads AI endpoints with synchronous website enrichment."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_workspace
from app.core.config import settings
from app.models.contact import Contact
from app.schemas.find_leads_ai import (
    AIImportLeadsRequest,
    AIImportLeadsResponse,
)
from app.schemas.scraping import (
    BusinessResult,
    BusinessSearchRequest,
    BusinessSearchResponse,
)
from app.services.scraping.enrichment_service import enrich_contact_data
from app.services.scraping.google_places import GooglePlacesError, GooglePlacesService
from app.services.telephony.telnyx import normalize_phone_number

router = APIRouter()

# Lead score threshold for import (only save contacts with score >= 80)
LEAD_SCORE_THRESHOLD = 80


@router.post("/search", response_model=BusinessSearchResponse)
async def search_businesses_ai(
    workspace_id: uuid.UUID,
    request: BusinessSearchRequest,
    current_user: CurrentUser,
    db: DB,
) -> BusinessSearchResponse:
    """Search for businesses using Google Places API.

    Same as regular Find Leads, but available at the /find-leads-ai endpoint.
    Returns a list of businesses matching the search query with their details.
    """
    # Verify workspace access
    await get_workspace(workspace_id, current_user, db)

    service = GooglePlacesService()
    try:
        results = await service.search_businesses(
            query=request.query,
            max_results=request.max_results,
        )

        business_results = [BusinessResult(**r) for r in results]

        return BusinessSearchResponse(
            results=business_results,
            total_found=len(business_results),
            query=request.query,
        )
    except GooglePlacesError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    finally:
        await service.close()


def _format_business_notes(lead: BusinessResult) -> str:
    """Format business context as notes."""
    lines = []

    # Categories
    if lead.types:
        # Clean up type names (remove underscores, title case)
        categories = [t.replace("_", " ").title() for t in lead.types[:5]]
        lines.append(f"Category: {', '.join(categories)}")

    # Address
    if lead.address:
        lines.append(f"Address: {lead.address}")

    # Rating
    if lead.rating:
        rating_str = f"{lead.rating}/5"
        if lead.review_count > 0:
            rating_str += f" ({lead.review_count} reviews)"
        lines.append(f"Rating: {rating_str}")

    # Website
    lines.append(f"Website: {lead.website or 'None'}")

    return "\n".join(lines)


@router.post("/import", response_model=AIImportLeadsResponse)
async def import_leads_ai(
    workspace_id: uuid.UUID,
    request: AIImportLeadsRequest,
    current_user: CurrentUser,
    db: DB,
) -> AIImportLeadsResponse:
    """Import selected leads as contacts with synchronous AI enrichment.

    Enrichment happens synchronously during import:
    - Leads are enriched before being saved to the database
    - Only leads with a lead score >= 80 are imported
    - Leads below the threshold are rejected immediately
    - No background processing for new imports

    For backward compatibility, the worker still processes any contacts
    with enrichment_status = "pending" that may exist from earlier imports.
    """
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    # Get existing phone numbers for duplicate detection
    phone_result = await db.execute(
        select(Contact.phone_number).where(Contact.workspace_id == workspace.id)
    )
    existing_phones: set[str] = set()
    for row in phone_result:
        if row[0]:
            existing_phones.add(normalize_phone_number(row[0]))

    imported = 0
    rejected_low_score = 0
    enrichment_failed = 0
    skipped_duplicates = 0
    skipped_no_phone = 0
    queued_for_enrichment = 0  # Always 0 now (synchronous)
    errors: list[str] = []

    for lead in request.leads:
        # Skip if no phone number
        if not lead.phone_number:
            skipped_no_phone += 1
            continue

        # Normalize and check for duplicates
        normalized_phone = normalize_phone_number(lead.phone_number)
        if normalized_phone in existing_phones:
            skipped_duplicates += 1
            continue

        try:
            # Build tags from business types
            tags = list(request.add_tags) if request.add_tags else []
            if lead.types:
                # Add first 3 business types as tags
                type_tags = [t.replace("_", " ").title() for t in lead.types[:3]]
                tags.extend(type_tags)

            # Build initial Google Places data for enrichment
            google_places_data: dict[str, Any] = {
                "google_places": {
                    "place_id": lead.place_id,
                    "rating": lead.rating,
                    "review_count": lead.review_count,
                    "types": lead.types,
                    "business_status": lead.business_status,
                },
            }

            # Enrich synchronously if enabled and website exists
            enrichment_result: dict[str, Any] = {
                "business_intel": google_places_data,
                "linkedin_url": None,
                "lead_score": 0,
                "enrichment_status": "skipped",
                "error": None,
            }

            if request.enable_enrichment and lead.website:
                enrichment_result = await enrich_contact_data(
                    website_url=lead.website,
                    company_name=lead.name,
                    google_places_data=google_places_data,
                    enable_ai=settings.enable_ai_enrichment,
                )

                if enrichment_result["enrichment_status"] == "failed":
                    enrichment_failed += 1
                    continue  # Skip importing if enrichment failed
            elif not lead.website:
                # No website = score of 0, will be rejected by threshold
                enrichment_result["lead_score"] = 0
                enrichment_result["enrichment_status"] = "skipped"

            # Check lead score threshold
            lead_score = enrichment_result["lead_score"]
            if lead_score < LEAD_SCORE_THRESHOLD:
                rejected_low_score += 1
                continue

            # Create contact (only if score >= 80)
            contact = Contact(
                workspace_id=workspace.id,
                first_name="Owner",
                company_name=lead.name,
                phone_number=normalized_phone,
                status=request.default_status,
                source="scraped_ai",
                tags=tags if tags else None,
                notes=_format_business_notes(lead),
                website_url=lead.website,
                linkedin_url=enrichment_result["linkedin_url"],
                enrichment_status=enrichment_result["enrichment_status"],
                business_intel=enrichment_result["business_intel"],
                lead_score=lead_score,
                # Already enriched, so set enriched_at now
                enriched_at=(
                    None
                    if enrichment_result["enrichment_status"] == "skipped"
                    else datetime.now(UTC)
                ),
            )
            db.add(contact)
            existing_phones.add(normalized_phone)
            imported += 1

        except Exception as e:
            errors.append(f"Failed to import {lead.name}: {e!s}")

    if imported > 0:
        await db.commit()

    return AIImportLeadsResponse(
        total=len(request.leads),
        imported=imported,
        rejected_low_score=rejected_low_score,
        enrichment_failed=enrichment_failed,
        skipped_duplicates=skipped_duplicates,
        skipped_no_phone=skipped_no_phone,
        queued_for_enrichment=queued_for_enrichment,
        errors=errors[:10],  # Limit errors in response
    )
