"""Contact endpoints."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_workspace
from app.core.config import settings
from app.models.contact import Contact
from app.schemas.contact import (
    ContactCreate,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
    QualificationSignals,
)
from app.services.contacts import ContactImportService, ContactService
from app.services.contacts.contact_import import ImportErrorDetail

router = APIRouter()


# Schema for sending a message to a contact
class SendMessageToContactRequest(BaseModel):
    """Request schema for sending a message to a contact."""

    body: str
    from_number: str | None = None  # Optional: specific phone number to send from


class MessageResponse(BaseModel):
    """Response schema for a message."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    direction: str
    channel: str
    body: str
    status: str
    is_ai: bool
    agent_id: uuid.UUID | None
    sent_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = None,
    sort_by: str | None = Query(
        None, description="Sort by: created_at, last_conversation, unread_first"
    ),
) -> ContactListResponse:
    """List contacts in a workspace."""
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    service = ContactService(db)
    result = await service.list_contacts(
        workspace_id=workspace.id,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        search=search,
        sort_by=sort_by,
    )

    return ContactListResponse(**result)


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    workspace_id: uuid.UUID,
    contact_in: ContactCreate,
    current_user: CurrentUser,
    db: DB,
) -> Contact:
    """Create a new contact."""
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    service = ContactService(db)
    return await service.create_contact(
        workspace_id=workspace.id,
        first_name=contact_in.first_name,
        last_name=contact_in.last_name,
        email=contact_in.email,
        phone_number=contact_in.phone_number,
        company_name=contact_in.company_name,
        contact_status=contact_in.status,
        tags=contact_in.tags,
        notes=contact_in.notes,
        source=contact_in.source,
    )


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    workspace_id: uuid.UUID,
    contact_id: int,
    current_user: CurrentUser,
    db: DB,
) -> Contact:
    """Get a specific contact."""
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    service = ContactService(db)
    return await service.get_contact(contact_id, workspace.id)


@router.put("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    workspace_id: uuid.UUID,
    contact_id: int,
    contact_in: ContactUpdate,
    current_user: CurrentUser,
    db: DB,
) -> Contact:
    """Update a contact."""
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    service = ContactService(db)
    update_data = contact_in.model_dump(exclude_unset=True)
    return await service.update_contact(contact_id, workspace.id, update_data)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    workspace_id: uuid.UUID,
    contact_id: int,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Delete a contact."""
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    service = ContactService(db)
    await service.delete_contact(contact_id, workspace.id)


class BulkDeleteRequest(BaseModel):
    """Request schema for bulk deleting contacts."""

    ids: list[int]


class BulkDeleteResponse(BaseModel):
    """Response schema for bulk delete operation."""

    deleted: int
    failed: int
    errors: list[str]


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_contacts(
    workspace_id: uuid.UUID,
    request: BulkDeleteRequest,
    current_user: CurrentUser,
    db: DB,
) -> BulkDeleteResponse:
    """Delete multiple contacts at once."""
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    service = ContactService(db)
    result = await service.bulk_delete_contacts(request.ids, workspace.id)

    return BulkDeleteResponse(**result)


@router.post("/{contact_id}/messages", response_model=MessageResponse)
async def send_message_to_contact(
    workspace_id: uuid.UUID,
    contact_id: int,
    message_in: SendMessageToContactRequest,
    current_user: CurrentUser,
    db: DB,
) -> Any:
    """Send an SMS message to a contact.

    This endpoint finds or creates a conversation for the contact and sends the message.
    """
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    service = ContactService(db)
    return await service.send_message(
        contact_id=contact_id,
        workspace_id=workspace.id,
        message_body=message_in.body,
        from_number=message_in.from_number,
        telnyx_api_key=settings.telnyx_api_key,
    )


class AIToggleRequest(BaseModel):
    """Request schema for toggling AI on a contact's conversation."""

    enabled: bool


class AIToggleResponse(BaseModel):
    """Response schema for AI toggle."""

    ai_enabled: bool
    conversation_id: uuid.UUID


@router.post("/{contact_id}/ai/toggle", response_model=AIToggleResponse)
async def toggle_contact_ai(
    workspace_id: uuid.UUID,
    contact_id: int,
    toggle_in: AIToggleRequest,
    current_user: CurrentUser,
    db: DB,
) -> AIToggleResponse:
    """Toggle AI for a contact's conversation.

    Finds an existing conversation for the contact or creates one if needed.
    """
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    service = ContactService(db)
    result = await service.toggle_ai(
        contact_id=contact_id,
        workspace_id=workspace.id,
        enabled=toggle_in.enabled,
    )

    return AIToggleResponse(**result)


class TimelineItem(BaseModel):
    """A unified timeline item."""

    id: uuid.UUID
    type: str  # "sms", "call", "appointment", "note"
    timestamp: datetime
    direction: str | None = None
    is_ai: bool = False
    content: str
    duration_seconds: int | None = None
    recording_url: str | None = None
    transcript: str | None = None
    status: str | None = None
    original_id: uuid.UUID
    original_type: str  # "sms_message", "call_record", "appointment", "note"

    class Config:
        from_attributes = True


@router.get("/{contact_id}/timeline", response_model=list[TimelineItem])
async def get_contact_timeline(
    workspace_id: uuid.UUID,
    contact_id: int,
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(100, ge=1, le=500),
) -> list[TimelineItem]:
    """Get the conversation timeline for a contact.

    Returns a unified timeline of SMS messages, calls, appointments, etc.
    """
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    service = ContactService(db)
    timeline_items_data = await service.get_contact_timeline(
        contact_id=contact_id,
        workspace_id=workspace.id,
        limit=limit,
    )

    # Convert dicts to TimelineItem models
    return [TimelineItem(**item) for item in timeline_items_data]


# ============================================================================
# CSV Import
# ============================================================================


class ImportResult(BaseModel):
    """Result of a CSV import operation."""

    total_rows: int
    successful: int
    failed: int
    skipped_duplicates: int
    errors: list[ImportErrorDetail]
    created_contacts: list[ContactResponse]


@router.post("/import", response_model=ImportResult)
async def import_contacts_csv(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    file: UploadFile,
    skip_duplicates: bool = Form(default=True),
    default_status: str = Form(default="new"),
    source: str = Form(default="csv_import"),
) -> ImportResult:
    """Import contacts from a CSV file.

    The CSV should have headers in the first row. Supported columns:
    - first_name (required): First name of the contact
    - last_name: Last name
    - email: Email address
    - phone_number (required): Phone number
    - company_name: Company or organization
    - status: Lead status (new, contacted, qualified, converted, lost)
    - tags: Comma-separated tags
    - notes: Additional notes

    Column names are case-insensitive and support common variations.
    """
    from app.services.contacts.contact_import import VALID_STATUSES

    workspace = await get_workspace(workspace_id, current_user, db)

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file",
        )

    if default_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be: {', '.join(VALID_STATUSES)}",
        )

    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {e!s}",
        ) from e

    # Use import service
    import_service = ContactImportService(db)
    try:
        result = await import_service.import_csv(
            workspace_id=workspace.id,
            file_content=content,
            skip_duplicates=skip_duplicates,
            default_status=default_status,
            source=source,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Convert to response format
    return ImportResult(
        total_rows=result.total_rows,
        successful=result.successful,
        failed=result.failed,
        skipped_duplicates=result.skipped_duplicates,
        errors=result.errors,
        created_contacts=[
            ContactResponse.model_validate(c) for c in result.created_contacts
        ],
    )


@router.get("/import/template")
async def get_import_template(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> dict[str, Any]:
    """Get CSV import template information."""
    await get_workspace(workspace_id, current_user, db)

    return ContactImportService.get_template_info()


# ============================================================================
# Lead Qualification
# ============================================================================


class QualifyContactResponse(BaseModel):
    """Response from analyzing and qualifying a contact."""

    success: bool
    contact_id: int | None = None
    lead_score: int = 0
    is_qualified: bool = False
    qualification_signals: QualificationSignals | None = None
    has_appointment: bool = False
    response_rate: float = 0.0
    message: str | None = None
    error: str | None = None


class BatchQualifyResponse(BaseModel):
    """Response from batch qualification analysis."""

    success: bool
    analyzed: int = 0
    qualified: int = 0
    errors: int = 0
    contacts: list[dict[str, Any]] = []
    error: str | None = None


@router.post("/{contact_id}/qualify", response_model=QualifyContactResponse)
async def qualify_contact(
    workspace_id: uuid.UUID,
    contact_id: int,
    current_user: CurrentUser,
    db: DB,
) -> QualifyContactResponse:
    """Analyze a contact's conversations and update their qualification status.

    Uses AI to extract BANT (Budget, Authority, Need, Timeline) signals from
    all conversations with the contact and calculates a lead score.

    The contact's is_qualified flag will be set to True if their score
    exceeds the qualification threshold (60).
    """
    from app.services.ai.qualification import analyze_and_qualify_contact

    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    # Verify contact exists in workspace
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.workspace_id == workspace.id,
        )
    )
    contact = result.scalar_one_or_none()

    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    # Run qualification analysis
    analysis = await analyze_and_qualify_contact(contact_id, db)

    if not analysis.get("success"):
        return QualifyContactResponse(
            success=False,
            error=analysis.get("error", "Unknown error"),
        )

    # Convert signals dict to QualificationSignals model if present
    signals = None
    if analysis.get("qualification_signals"):
        signals = QualificationSignals(**analysis["qualification_signals"])

    return QualifyContactResponse(
        success=True,
        contact_id=analysis.get("contact_id"),
        lead_score=analysis.get("lead_score", 0),
        is_qualified=analysis.get("is_qualified", False),
        qualification_signals=signals,
        has_appointment=analysis.get("has_appointment", False),
        response_rate=analysis.get("response_rate", 0.0),
        message=analysis.get("message"),
    )


@router.get("/{contact_id}/qualification", response_model=QualifyContactResponse)
async def get_contact_qualification(
    workspace_id: uuid.UUID,
    contact_id: int,
    current_user: CurrentUser,
    db: DB,
) -> QualifyContactResponse:
    """Get the current qualification status of a contact without re-analyzing."""
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    # Get contact
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.workspace_id == workspace.id,
        )
    )
    contact = result.scalar_one_or_none()

    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    # Convert signals dict to QualificationSignals model if present
    signals = None
    if contact.qualification_signals:
        signals = QualificationSignals(**contact.qualification_signals)

    return QualifyContactResponse(
        success=True,
        contact_id=contact.id,
        lead_score=contact.lead_score,
        is_qualified=contact.is_qualified,
        qualification_signals=signals,
    )


@router.post("/qualify/batch", response_model=BatchQualifyResponse)
async def batch_qualify_contacts(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(50, ge=1, le=100),
) -> BatchQualifyResponse:
    """Analyze and qualify multiple contacts in the workspace.

    Prioritizes contacts that:
    - Have never been analyzed
    - Are in 'new' or 'contacted' status

    This is useful for batch processing leads that need qualification.
    """
    from app.services.ai.qualification import batch_analyze_contacts

    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    # Run batch analysis
    result = await batch_analyze_contacts(str(workspace.id), db, limit)

    if not result.get("success"):
        return BatchQualifyResponse(
            success=False,
            error=result.get("error", "Unknown error"),
        )

    return BatchQualifyResponse(
        success=True,
        analyzed=result.get("analyzed", 0),
        qualified=result.get("qualified", 0),
        errors=result.get("errors", 0),
        contacts=result.get("contacts", []),
    )
