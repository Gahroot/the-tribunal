"""Find Leads AI endpoints with website enrichment."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_workspace
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
from app.services.scraping.google_places import GooglePlacesError, GooglePlacesService
from app.services.telephony.telnyx import normalize_phone_number

router = APIRouter()


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
    """Import selected leads as contacts with AI enrichment.

    Creates contacts from the selected business results.
    Skips duplicates based on phone number.
    Queues contacts with websites for background enrichment.
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
    skipped_duplicates = 0
    skipped_no_phone = 0
    queued_for_enrichment = 0
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

            # Determine enrichment status
            has_website = bool(lead.website)
            enrichment_status = None
            if request.enable_enrichment:
                enrichment_status = "pending" if has_website else "skipped"

            # Build initial business_intel with Google Places data
            business_intel = {
                "google_places": {
                    "place_id": lead.place_id,
                    "rating": lead.rating,
                    "review_count": lead.review_count,
                    "types": lead.types,
                    "business_status": lead.business_status,
                },
            }

            # Create contact
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
                enrichment_status=enrichment_status,
                business_intel=business_intel,
            )
            db.add(contact)
            existing_phones.add(normalized_phone)
            imported += 1

            if enrichment_status == "pending":
                queued_for_enrichment += 1

        except Exception as e:
            errors.append(f"Failed to import {lead.name}: {e!s}")

    if imported > 0:
        await db.commit()

    return AIImportLeadsResponse(
        total=len(request.leads),
        imported=imported,
        skipped_duplicates=skipped_duplicates,
        skipped_no_phone=skipped_no_phone,
        queued_for_enrichment=queued_for_enrichment,
        errors=errors[:10],  # Limit errors in response
    )
