"""Contact endpoints."""

import uuid
from datetime import datetime
from math import ceil

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.core.config import settings
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.phone_number import PhoneNumber
from app.schemas.contact import ContactCreate, ContactListResponse, ContactResponse, ContactUpdate
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
) -> ContactListResponse:
    """List contacts in a workspace."""
    # Verify workspace access
    workspace = await get_workspace(workspace_id, current_user, db)

    # Build query
    query = select(Contact).where(Contact.workspace_id == workspace.id)

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

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.order_by(Contact.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute query
    result = await db.execute(query)
    contacts = result.scalars().all()

    return ContactListResponse(
        items=[ContactResponse.model_validate(c) for c in contacts],
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
            timeline_items.append(
                TimelineItem(
                    id=msg.id,
                    type="sms",
                    timestamp=msg.created_at,
                    direction=msg.direction,
                    is_ai=msg.is_ai,
                    content=msg.body,
                    status=msg.status,
                    original_id=msg.id,
                    original_type="sms_message",
                )
            )

    # Sort by timestamp (oldest first)
    timeline_items.sort(key=lambda x: x.timestamp)

    # Return the last `limit` items
    return timeline_items[-limit:]
