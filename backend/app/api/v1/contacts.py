"""Contact endpoints."""

import uuid
from math import ceil

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.contact import Contact
from app.models.workspace import Workspace
from app.schemas.contact import ContactCreate, ContactListResponse, ContactResponse, ContactUpdate

router = APIRouter()


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
