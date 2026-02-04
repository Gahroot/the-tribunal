"""Contact repository - data access layer for contact operations."""

import uuid
from typing import Any

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.services.telephony.telnyx import normalize_phone_number

logger = structlog.get_logger()


async def list_contacts_paginated(
    workspace_id: uuid.UUID,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    status_filter: str | None = None,
    search: str | None = None,
    sort_by: str | None = None,
) -> tuple[Any, int]:
    """Build and execute contact list query with filters and pagination.

    Args:
        workspace_id: The workspace UUID
        db: Database session
        page: Page number (1-indexed)
        page_size: Number of items per page
        status_filter: Optional status filter
        search: Optional search term
        sort_by: Optional sort field (created_at, last_conversation, unread_first)

    Returns:
        Tuple of (rows, total_count) where rows contain contact data with conversation stats
    """
    log = logger.bind(workspace_id=str(workspace_id), page=page, page_size=page_size)

    # Subquery to get conversation data per contact (aggregated across all conversations)
    conv_subquery = (
        select(
            Conversation.contact_id,
            func.sum(Conversation.unread_count).label("total_unread"),
            func.max(Conversation.last_message_at).label("max_message_at"),
            # Get the direction of the most recent message
            func.max(Conversation.last_message_direction).label("last_direction"),
        )
        .where(Conversation.workspace_id == workspace_id)
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
        .where(Contact.workspace_id == workspace_id)
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
    base_count_query = select(Contact).where(Contact.workspace_id == workspace_id)
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

    # Apply sorting (always include Contact.id as final sort key for stable pagination)
    if sort_by == "unread_first":
        # Unread contacts first (by unread count desc), then by last message time
        query = query.order_by(
            conv_subquery.c.total_unread.desc().nullslast(),
            conv_subquery.c.max_message_at.desc().nullslast(),
            Contact.id.desc(),
        )
    elif sort_by == "last_conversation":
        # Sort by most recent conversation first, contacts with no conversation go last
        query = query.order_by(
            conv_subquery.c.max_message_at.desc().nullslast(),
            Contact.id.desc(),
        )
    else:
        query = query.order_by(Contact.created_at.desc(), Contact.id.desc())

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute query
    result = await db.execute(query)
    rows = result.all()

    log.info("contacts_listed", total=total, returned=len(rows))

    return rows, total


async def get_contact_by_id(
    contact_id: int,
    workspace_id: uuid.UUID,
    db: AsyncSession,
) -> Contact | None:
    """Get a specific contact by ID.

    Args:
        contact_id: The contact ID
        workspace_id: The workspace UUID
        db: Database session

    Returns:
        Contact object or None if not found
    """
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


async def create_contact(
    workspace_id: uuid.UUID,
    db: AsyncSession,
    first_name: str,
    last_name: str | None = None,
    email: str | None = None,
    phone_number: str | None = None,
    company_name: str | None = None,
    status: str = "new",
    tags: list[str] | None = None,
    notes: str | None = None,
    source: str | None = None,
) -> Contact:
    """Create a new contact.

    Args:
        workspace_id: The workspace UUID
        db: Database session
        first_name: First name (required)
        last_name: Last name
        email: Email address
        phone_number: Phone number
        company_name: Company name
        status: Contact status
        tags: List of tags
        notes: Additional notes
        source: Source of the contact

    Returns:
        Created contact
    """
    contact = Contact(
        workspace_id=workspace_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone_number=phone_number,
        company_name=company_name,
        status=status,
        tags=tags,
        notes=notes,
        source=source,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


async def update_contact(
    contact: Contact,
    db: AsyncSession,
    update_data: dict[str, Any],
) -> Contact:
    """Update a contact with new data.

    Args:
        contact: Contact object to update
        db: Database session
        update_data: Dictionary of fields to update

    Returns:
        Updated contact
    """
    for field, value in update_data.items():
        setattr(contact, field, value)

    await db.commit()
    await db.refresh(contact)
    return contact


async def delete_contact(
    contact: Contact,
    db: AsyncSession,
) -> None:
    """Delete a contact.

    Args:
        contact: Contact object to delete
        db: Database session
    """
    await db.delete(contact)
    await db.commit()


async def bulk_delete_contacts(
    contact_ids: list[int],
    workspace_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[int, list[str]]:
    """Delete multiple contacts at once.

    Args:
        contact_ids: List of contact IDs to delete
        workspace_id: The workspace UUID
        db: Database session

    Returns:
        Tuple of (deleted_count, list_of_errors)
    """
    errors: list[str] = []

    # Single query to fetch all contacts at once
    result = await db.execute(
        select(Contact).where(
            Contact.id.in_(contact_ids),
            Contact.workspace_id == workspace_id,
        )
    )
    contacts = result.scalars().all()

    # Track found contact IDs
    found_ids = {contact.id for contact in contacts}

    # Track missing contact IDs
    for contact_id in contact_ids:
        if contact_id not in found_ids:
            errors.append(f"Contact {contact_id} not found")

    # Delete all found contacts in one operation
    # Database CASCADE will handle related deletions
    for contact in contacts:
        await db.delete(contact)

    await db.commit()

    deleted = len(contacts)

    return deleted, errors


async def get_contact_timeline(
    contact_id: int,
    workspace_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get the conversation timeline for a contact.

    Returns a unified timeline of SMS messages, calls, appointments, etc.

    Args:
        contact_id: The contact ID
        workspace_id: The workspace UUID
        db: Database session
        limit: Maximum items to return

    Returns:
        List of timeline items (dicts)
    """
    log = logger.bind(contact_id=contact_id, workspace_id=str(workspace_id))

    # Get contact
    contact = await get_contact_by_id(contact_id, workspace_id, db)
    if not contact:
        return []

    timeline_items: list[dict[str, Any]] = []

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

    # Get all conversation IDs
    conversation_ids = [conv.id for conv in conversations]

    if conversation_ids:
        # Single query to get all messages from all conversations
        msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id.in_(conversation_ids))
            .order_by(Message.created_at.desc())
        )
        all_messages = msg_result.scalars().all()

        # Group messages by conversation_id in memory
        messages_by_conv: dict[uuid.UUID, list[Message]] = {}
        for msg in all_messages:
            if msg.conversation_id not in messages_by_conv:
                messages_by_conv[msg.conversation_id] = []
            messages_by_conv[msg.conversation_id].append(msg)

        # Process messages for each conversation, limiting in memory
        for conversation in conversations:
            messages = messages_by_conv.get(conversation.id, [])
            # Limit messages per conversation in memory
            for msg in messages[:limit]:
                # Determine type based on channel
                item_type = "call" if msg.channel == "voice" else msg.channel

                timeline_items.append({
                    "id": msg.id,
                    "type": item_type,
                    "timestamp": msg.created_at,
                    "direction": msg.direction,
                    "is_ai": msg.is_ai,
                    "content": msg.body,
                    "duration_seconds": msg.duration_seconds,
                    "recording_url": msg.recording_url,
                    "transcript": msg.transcript,
                    "status": msg.status,
                    "original_id": msg.id,
                    "original_type": f"{msg.channel}_message",
                })

    # Sort by timestamp (oldest first)
    timeline_items.sort(key=lambda x: x["timestamp"])

    log.info("timeline_retrieved", item_count=len(timeline_items))

    # Return the last `limit` items
    return timeline_items[-limit:]


async def list_contact_ids(
    workspace_id: uuid.UUID,
    db: AsyncSession,
    status_filter: str | None = None,
    search: str | None = None,
) -> tuple[list[int], int]:
    """Get all contact IDs matching filters (for Select All functionality).

    Args:
        workspace_id: The workspace UUID
        db: Database session
        status_filter: Optional status filter
        search: Optional search term

    Returns:
        Tuple of (list of contact IDs, total count)
    """
    query = select(Contact.id).where(Contact.workspace_id == workspace_id)

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

    query = query.order_by(Contact.id)

    result = await db.execute(query)
    ids = [row[0] for row in result.all()]

    return ids, len(ids)


async def find_or_create_conversation(
    contact_id: int,
    workspace_id: uuid.UUID,
    contact_phone: str,
    workspace_phone: str,
    db: AsyncSession,
) -> Conversation:
    """Find or create a conversation for a contact.

    Args:
        contact_id: The contact ID
        workspace_id: The workspace UUID
        contact_phone: Contact's phone number (normalized)
        workspace_phone: Workspace phone number to use
        db: Database session

    Returns:
        Conversation object
    """
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
        normalized_contact_phone = normalize_phone_number(contact_phone)
        conv_result = await db.execute(
            select(Conversation)
            .where(
                Conversation.workspace_id == workspace_id,
                or_(
                    Conversation.contact_phone == contact_phone,
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
        conversation = Conversation(
            workspace_id=workspace_id,
            contact_id=contact_id,
            workspace_phone=workspace_phone,
            contact_phone=normalize_phone_number(contact_phone),
            channel="sms",
            ai_enabled=False,
        )
        db.add(conversation)

    return conversation
