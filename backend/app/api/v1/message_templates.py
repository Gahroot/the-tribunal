"""Message template management endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.message_template import MessageTemplate
from app.models.workspace import Workspace
from app.schemas.message_template import (
    MessageTemplateCreate,
    MessageTemplateResponse,
    PaginatedMessageTemplates,
)

router = APIRouter()


@router.get("", response_model=PaginatedMessageTemplates)
async def list_message_templates(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> PaginatedMessageTemplates:
    """List message templates in a workspace."""
    query = select(MessageTemplate).where(MessageTemplate.workspace_id == workspace_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(MessageTemplate.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    templates = result.scalars().all()

    return PaginatedMessageTemplates(
        items=[MessageTemplateResponse.model_validate(t) for t in templates],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )


@router.post("", response_model=MessageTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_message_template(
    workspace_id: uuid.UUID,
    template_in: MessageTemplateCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> MessageTemplate:
    """Create a new message template."""
    template = MessageTemplate(
        workspace_id=workspace_id,
        **template_in.model_dump(),
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message_template(
    workspace_id: uuid.UUID,
    template_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete a message template."""
    result = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.id == template_id,
            MessageTemplate.workspace_id == workspace_id,
        )
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message template not found",
        )

    await db.delete(template)
    await db.commit()
