"""Contact endpoints."""

import csv
import io
import uuid
from datetime import datetime
from math import ceil
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.core.config import settings
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.phone_number import PhoneNumber
from app.schemas.contact import (
    ContactCreate,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
    ContactWithConversationResponse,
    QualificationSignals,
)
from app.services.telephony.telnyx import TelnyxSMSService, normalize_phone_number

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

    # Subquery to get conversation data per contact (aggregated across all conversations)
    conv_subquery = (
        select(
            Conversation.contact_id,
            func.sum(Conversation.unread_count).label("total_unread"),
            func.max(Conversation.last_message_at).label("max_message_at"),
            # Get the direction of the most recent message
            func.max(Conversation.last_message_direction).label("last_direction"),
        )
        .where(Conversation.workspace_id == workspace.id)
        .where(Conversation.contact_id.isnot(None))
        .group_by(Conversation.contact_id)
        .subquery()
    )

    # Build query with conversation data
    query = (
        select(
            Contact,
            func.coalesce(conv_subquery.c.total_unread, 0).label("unread_count"),
            conv_subquery.c.max_message_at.label("last_message_at"),
            conv_subquery.c.last_direction.label("last_message_direction"),
        )
        .outerjoin(conv_subquery, Contact.id == conv_subquery.c.contact_id)
        .where(Contact.workspace_id == workspace.id)
    )

    # Apply filters
    if status_filter:
        query = query.where(Contact.status == status_filter)

    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Contact.first_name.ilike(search_term))
            | (Contact.last_name.ilike(search_term))
            | (Contact.email.ilike(search_term))
            | (Contact.phone_number.ilike(search_term))
            | (Contact.company_name.ilike(search_term))
        )

    # Get total count (from base contact query without conversation columns)
    base_count_query = select(Contact).where(Contact.workspace_id == workspace.id)
    if status_filter:
        base_count_query = base_count_query.where(Contact.status == status_filter)
    if search:
        search_term = f"%{search}%"
        base_count_query = base_count_query.where(
            (Contact.first_name.ilike(search_term))
            | (Contact.last_name.ilike(search_term))
            | (Contact.email.ilike(search_term))
            | (Contact.phone_number.ilike(search_term))
            | (Contact.company_name.ilike(search_term))
        )
    count_query = select(func.count()).select_from(base_count_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply sorting
    if sort_by == "unread_first":
        # Unread contacts first (by unread count desc), then by last message time
        query = query.order_by(
            conv_subquery.c.total_unread.desc().nullslast(),
            conv_subquery.c.max_message_at.desc().nullslast(),
        )
    elif sort_by == "last_conversation":
        # Sort by most recent conversation first, contacts with no conversation go last
        query = query.order_by(conv_subquery.c.max_message_at.desc().nullslast())
    else:
        query = query.order_by(Contact.created_at.desc())

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute query
    result = await db.execute(query)
    rows = result.all()

    # Build response with conversation data
    items = []
    for row in rows:
        contact = row[0]  # Contact object
        contact_data = ContactWithConversationResponse.model_validate(contact)
        contact_data.unread_count = row[1] or 0
        contact_data.last_message_at = row[2]
        contact_data.last_message_direction = row[3]
        items.append(contact_data)

    return ContactListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total > 0 else 1,
    )


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

    # Create contact
    contact = Contact(
        workspace_id=workspace.id,
        first_name=contact_in.first_name,
        last_name=contact_in.last_name,
        email=contact_in.email,
        phone_number=contact_in.phone_number,
        company_name=contact_in.company_name,
        status=contact_in.status,
        tags=contact_in.tags,
        notes=contact_in.notes,
        source=contact_in.source,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    return contact


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

    return contact


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

    # Update fields
    update_data = contact_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contact, field, value)

    await db.commit()
    await db.refresh(contact)

    return contact


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

    await db.delete(contact)
    await db.commit()


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

    if not request.ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No contact IDs provided",
        )

    deleted = 0
    errors: list[str] = []

    for contact_id in request.ids:
        result = await db.execute(
            select(Contact).where(
                Contact.id == contact_id,
                Contact.workspace_id == workspace.id,
            )
        )
        contact = result.scalar_one_or_none()

        if contact is None:
            errors.append(f"Contact {contact_id} not found")
            continue

        await db.delete(contact)
        deleted += 1

    await db.commit()

    return BulkDeleteResponse(
        deleted=deleted,
        failed=len(errors),
        errors=errors,
    )


@router.post("/{contact_id}/messages", response_model=MessageResponse)
async def send_message_to_contact(
    workspace_id: uuid.UUID,
    contact_id: int,
    message_in: SendMessageToContactRequest,
    current_user: CurrentUser,
    db: DB,
) -> Message:
    """Send an SMS message to a contact.

    This endpoint finds or creates a conversation for the contact and sends the message.
    """
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

    if not contact.phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact does not have a phone number",
        )

    # Get workspace phone number for sending
    if message_in.from_number:
        # Use the specified phone number
        phone_result = await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.workspace_id == workspace_id,
                PhoneNumber.phone_number == message_in.from_number,
                PhoneNumber.sms_enabled.is_(True),
                PhoneNumber.is_active.is_(True),
            )
        )
        workspace_phone = phone_result.scalar_one_or_none()
        if workspace_phone is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Specified phone number not found or not SMS-enabled",
            )
    else:
        # Use the first available SMS-enabled phone number
        phone_result = await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.workspace_id == workspace_id,
                PhoneNumber.sms_enabled.is_(True),
                PhoneNumber.is_active.is_(True),
            ).limit(1)
        )
        workspace_phone = phone_result.scalar_one_or_none()
        if workspace_phone is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No SMS-enabled phone number configured for this workspace",
            )

    # Check for Telnyx API key
    telnyx_api_key = settings.telnyx_api_key
    if not telnyx_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS service not configured",
        )

    # Send message via Telnyx (this creates/gets conversation automatically)
    sms_service = TelnyxSMSService(telnyx_api_key)
    try:
        message = await sms_service.send_message(
            to_number=contact.phone_number,
            from_number=workspace_phone.phone_number,
            body=message_in.body,
            db=db,
            workspace_id=workspace_id,
        )
        return message
    finally:
        await sms_service.close()


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

    if not contact.phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contact does not have a phone number",
        )

    # Normalize the contact phone number for matching
    normalized_contact_phone = normalize_phone_number(contact.phone_number)

    # Try to find existing conversation by contact_id first (get most recent)
    conv_result = await db.execute(
        select(Conversation)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.contact_id == contact_id,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    conversation = conv_result.scalars().first()

    # If not found by contact_id, try finding by phone number
    if conversation is None:
        conv_result = await db.execute(
            select(Conversation)
            .where(
                Conversation.workspace_id == workspace_id,
                or_(
                    Conversation.contact_phone == contact.phone_number,
                    Conversation.contact_phone == normalized_contact_phone,
                ),
            )
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        conversation = conv_result.scalars().first()

        # If found by phone, link it to this contact
        if conversation is not None:
            conversation.contact_id = contact_id

    # If still no conversation, create one
    if conversation is None:
        # Get a workspace phone number
        phone_result = await db.execute(
            select(PhoneNumber).where(
                PhoneNumber.workspace_id == workspace_id,
                PhoneNumber.sms_enabled.is_(True),
                PhoneNumber.is_active.is_(True),
            ).limit(1)
        )
        workspace_phone = phone_result.scalar_one_or_none()

        if workspace_phone is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No SMS-enabled phone number configured for this workspace",
            )

        # Create conversation
        conversation = Conversation(
            workspace_id=workspace_id,
            contact_id=contact_id,
            workspace_phone=workspace_phone.phone_number,
            contact_phone=normalized_contact_phone,
            channel="sms",
            ai_enabled=toggle_in.enabled,
        )
        db.add(conversation)
    else:
        # Update existing conversation
        conversation.ai_enabled = toggle_in.enabled

    await db.commit()
    await db.refresh(conversation)

    return AIToggleResponse(
        ai_enabled=conversation.ai_enabled,
        conversation_id=conversation.id,
    )


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

    # Get contact
    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.workspace_id == workspace.id,
        )
    )
    contact = contact_result.scalar_one_or_none()

    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    timeline_items: list[TimelineItem] = []

    # Normalize contact phone for matching
    normalized_contact_phone = (
        normalize_phone_number(contact.phone_number) if contact.phone_number else None
    )

    # Get conversations for this contact (by contact_id or phone number)
    conv_query = select(Conversation).where(
        Conversation.workspace_id == workspace_id,
    )

    if contact.phone_number and normalized_contact_phone:
        conv_query = conv_query.where(
            or_(
                Conversation.contact_id == contact_id,
                Conversation.contact_phone == contact.phone_number,
                Conversation.contact_phone == normalized_contact_phone,
            )
        )
    else:
        conv_query = conv_query.where(Conversation.contact_id == contact_id)

    conv_result = await db.execute(conv_query)
    conversations = conv_result.scalars().all()

    # Get all messages from these conversations
    for conversation in conversations:
        msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = msg_result.scalars().all()

        for msg in messages:
            # Determine type based on channel
            item_type = "call" if msg.channel == "voice" else msg.channel

            timeline_items.append(
                TimelineItem(
                    id=msg.id,
                    type=item_type,
                    timestamp=msg.created_at,
                    direction=msg.direction,
                    is_ai=msg.is_ai,
                    content=msg.body,
                    duration_seconds=msg.duration_seconds,
                    recording_url=msg.recording_url,
                    transcript=msg.transcript,
                    status=msg.status,
                    original_id=msg.id,
                    original_type=f"{msg.channel}_message",
                )
            )

    # Sort by timestamp (oldest first)
    timeline_items.sort(key=lambda x: x.timestamp)

    # Return the last `limit` items
    return timeline_items[-limit:]


# ============================================================================
# CSV Import
# ============================================================================


class ImportErrorDetail(BaseModel):
    """Detail about a single import error."""

    row: int
    field: str | None = None
    error: str


class ImportResult(BaseModel):
    """Result of a CSV import operation."""

    total_rows: int
    successful: int
    failed: int
    skipped_duplicates: int
    errors: list[ImportErrorDetail]
    created_contacts: list[ContactResponse]


# Expected CSV columns and their mappings
CSV_FIELD_MAPPING = {
    "first_name": ["first_name", "first name", "firstname", "first", "name"],
    "last_name": ["last_name", "last name", "lastname", "last", "surname"],
    "email": ["email", "email_address", "email address", "e-mail"],
    "phone_number": ["phone_number", "phone number", "phone", "mobile", "cell", "telephone", "tel"],
    "company_name": ["company_name", "company name", "company", "organization", "org"],
    "status": ["status", "lead_status", "lead status"],
    "tags": ["tags", "tag", "labels"],
    "notes": ["notes", "note", "comments", "comment", "description"],
}

VALID_STATUSES = {"new", "contacted", "qualified", "converted", "lost"}


def find_csv_column(headers: list[str] | tuple[str, ...], field_name: str) -> str | None:
    """Find the CSV column that matches a field name."""
    possible_names = CSV_FIELD_MAPPING.get(field_name, [field_name])
    headers_lower = [h.lower().strip() for h in headers]

    for name in possible_names:
        if name.lower() in headers_lower:
            idx = headers_lower.index(name.lower())
            return headers[idx]
    return None


def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email:
        return True
    import re
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def clean_phone_number(phone: str) -> str | None:
    """Clean and validate phone number."""
    if not phone:
        return None
    # Remove common formatting characters
    cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
    if len(cleaned) < 10:
        return None
    return normalize_phone_number(cleaned)


def _get_csv_field(
    row: dict[str, str],
    column_mapping: dict[str, str | None],
    field: str,
) -> str | None:
    """Extract and clean a field from a CSV row."""
    col = column_mapping.get(field)
    if not col:
        return None
    return row.get(col, "").strip() or None


def _read_csv_content(file_content: bytes) -> str:
    """Decode CSV file content, trying UTF-8 first then latin-1."""
    try:
        return file_content.decode("utf-8")
    except UnicodeDecodeError:
        return file_content.decode("latin-1")


def _process_csv_row(  # noqa: PLR0911
    row: dict[str, str],
    row_num: int,
    column_mapping: dict[str, str | None],
    default_status: str,
    existing_phones: set[str],
    skip_duplicates: bool,
    errors: list[ImportErrorDetail],
) -> tuple[dict[str, Any] | None, bool]:
    """Process a single CSV row and return contact data or None if invalid.

    Returns:
        Tuple of (contact_data or None, is_duplicate)
    """
    first_name = _get_csv_field(row, column_mapping, "first_name") or ""
    if not first_name:
        errors.append(ImportErrorDetail(
            row=row_num, field="first_name", error="First name is required"
        ))
        return None, False

    phone_raw = _get_csv_field(row, column_mapping, "phone_number") or ""
    phone_number = clean_phone_number(phone_raw)
    if not phone_number:
        errors.append(ImportErrorDetail(
            row=row_num, field="phone_number", error=f"Invalid phone: {phone_raw}"
        ))
        return None, False

    if skip_duplicates and phone_number in existing_phones:
        return None, True

    email = _get_csv_field(row, column_mapping, "email")
    if email and not validate_email(email):
        errors.append(ImportErrorDetail(
            row=row_num, field="email", error=f"Invalid email: {email}"
        ))
        return None, False

    status_val = (_get_csv_field(row, column_mapping, "status") or "").lower()
    contact_status = default_status
    if status_val and status_val in VALID_STATUSES:
        contact_status = status_val
    elif status_val:
        errors.append(ImportErrorDetail(
            row=row_num, field="status",
            error=f"Invalid status '{status_val}', using default"
        ))

    tags_raw = _get_csv_field(row, column_mapping, "tags")
    tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None

    return {
        "first_name": first_name,
        "last_name": _get_csv_field(row, column_mapping, "last_name"),
        "email": email,
        "phone_number": phone_number,
        "company_name": _get_csv_field(row, column_mapping, "company_name"),
        "status": contact_status,
        "tags": tags_list,
        "notes": _get_csv_field(row, column_mapping, "notes"),
    }, False


@router.post("/import", response_model=ImportResult)
async def import_contacts_csv(  # noqa: PLR0912
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
        text_content = _read_csv_content(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {e!s}",
        ) from e

    try:
        reader = csv.DictReader(io.StringIO(text_content))
        headers = reader.fieldnames or []
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV: {e!s}",
        ) from e

    if not headers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file has no headers",
        )

    headers_list = list(headers)
    column_mapping = {f: find_csv_column(headers_list, f) for f in CSV_FIELD_MAPPING}

    if not column_mapping["first_name"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must have a 'first_name' column",
        )
    if not column_mapping["phone_number"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must have a 'phone_number' column",
        )

    existing_phones: set[str] = set()
    if skip_duplicates:
        phone_result = await db.execute(
            select(Contact.phone_number).where(
                Contact.workspace_id == workspace.id
            )
        )
        for db_row in phone_result:
            if db_row[0]:
                existing_phones.add(normalize_phone_number(db_row[0]))

    errors: list[ImportErrorDetail] = []
    created_contacts: list[Contact] = []
    skipped_duplicates_count = 0
    row_num = 1

    for row in reader:
        row_num += 1
        contact_data, is_dup = _process_csv_row(
            row, row_num, column_mapping, default_status,
            existing_phones, skip_duplicates, errors
        )

        if is_dup:
            skipped_duplicates_count += 1
            continue

        if not contact_data:
            continue

        contact = Contact(
            workspace_id=workspace.id,
            source=source,
            **contact_data,
        )
        db.add(contact)
        created_contacts.append(contact)
        existing_phones.add(contact_data["phone_number"])

    if created_contacts:
        await db.commit()
        for contact in created_contacts:
            await db.refresh(contact)

    return ImportResult(
        total_rows=row_num - 1,
        successful=len(created_contacts),
        failed=len([e for e in errors if "using default" not in e.error]),
        skipped_duplicates=skipped_duplicates_count,
        errors=errors[:100],
        created_contacts=[
            ContactResponse.model_validate(c) for c in created_contacts[:100]
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

    example_rows = [
        "first_name,last_name,phone_number,email,company_name,status,tags,notes",
        'John,Doe,+15551234567,john@example.com,Acme Inc,new,"vip,priority",',
        "Jane,Smith,5559876543,jane@example.com,Tech Corp,contacted,lead,",
    ]

    return {
        "columns": [
            {"name": "first_name", "required": True, "description": "First name"},
            {"name": "last_name", "required": False, "description": "Last name"},
            {"name": "email", "required": False, "description": "Email address"},
            {"name": "phone_number", "required": True, "description": "Phone"},
            {"name": "company_name", "required": False, "description": "Company"},
            {"name": "status", "required": False, "description": "Lead status"},
            {"name": "tags", "required": False, "description": "Comma-separated"},
            {"name": "notes", "required": False, "description": "Notes"},
        ],
        "example_csv": "\n".join(example_rows),
        "supported_aliases": CSV_FIELD_MAPPING,
    }


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
