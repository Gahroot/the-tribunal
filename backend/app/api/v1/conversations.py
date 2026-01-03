"""Conversations and messages endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.core.config import settings
from app.models.agent import Agent
from app.models.conversation import Conversation, Message
from app.models.workspace import Workspace
from app.services.telephony.telnyx import TelnyxSMSService

router = APIRouter()


# Schemas
class MessageCreate(BaseModel):
    """Schema for sending a message."""

    body: str


class MessageResponse(BaseModel):
    """Message response schema."""

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


class ConversationResponse(BaseModel):
    """Conversation response schema."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    contact_id: int | None
    workspace_phone: str
    contact_phone: str
    status: str
    channel: str
    assigned_agent_id: uuid.UUID | None
    ai_enabled: bool
    ai_paused: bool
    unread_count: int
    last_message_preview: str | None
    last_message_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationWithMessages(ConversationResponse):
    """Conversation with messages."""

    messages: list[MessageResponse]


class PaginatedConversations(BaseModel):
    """Paginated conversations response."""

    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int
    pages: int


class AIToggle(BaseModel):
    """AI toggle request."""

    enabled: bool


class AgentAssign(BaseModel):
    """Agent assignment request."""

    agent_id: uuid.UUID | None


# Endpoints
@router.get("", response_model=PaginatedConversations)
async def list_conversations(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status_filter: str | None = None,
    channel_filter: str | None = None,
    unread_only: bool = False,
) -> PaginatedConversations:
    """List conversations in a workspace."""
    # Build query
    query = select(Conversation).where(Conversation.workspace_id == workspace_id)

    if status_filter:
        query = query.where(Conversation.status == status_filter)
    if channel_filter:
        query = query.where(Conversation.channel == channel_filter)
    if unread_only:
        query = query.where(Conversation.unread_count > 0)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(Conversation.last_message_at.desc().nullslast())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    conversations = result.scalars().all()

    return PaginatedConversations(
        items=[ConversationResponse.model_validate(c) for c in conversations],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    limit: int = Query(50, ge=1, le=200),
) -> ConversationWithMessages:
    """Get a conversation with its messages."""
    # Get conversation
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Get messages
    messages_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(reversed(messages_result.scalars().all()))

    # Mark as read
    conversation.unread_count = 0
    await db.commit()

    return ConversationWithMessages(
        **ConversationResponse.model_validate(conversation).model_dump(),
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_in: MessageCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Message:
    """Send a message in a conversation."""
    # Get conversation
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Check for Telnyx API key
    telnyx_api_key = settings.telnyx_api_key
    if not telnyx_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS service not configured",
        )

    # Send message via Telnyx
    sms_service = TelnyxSMSService(telnyx_api_key)
    try:
        message = await sms_service.send_message(
            to_number=conversation.contact_phone,
            from_number=conversation.workspace_phone,
            body=message_in.body,
            db=db,
            workspace_id=workspace_id,
        )
        return message
    finally:
        await sms_service.close()


@router.post("/{conversation_id}/ai/toggle")
async def toggle_ai(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    toggle: AIToggle,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, bool]:
    """Toggle AI for a conversation."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    conversation.ai_enabled = toggle.enabled
    await db.commit()

    return {"ai_enabled": conversation.ai_enabled}


@router.post("/{conversation_id}/ai/pause")
async def pause_ai(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, bool]:
    """Pause AI for a conversation (temporary)."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    conversation.ai_paused = True
    await db.commit()

    return {"ai_paused": True}


@router.post("/{conversation_id}/ai/resume")
async def resume_ai(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, bool]:
    """Resume AI for a conversation."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    conversation.ai_paused = False
    await db.commit()

    return {"ai_paused": False}


@router.post("/{conversation_id}/assign")
async def assign_agent(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    assign: AgentAssign,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, uuid.UUID | None]:
    """Assign an agent to a conversation."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Verify agent exists and belongs to workspace
    if assign.agent_id:
        agent_result = await db.execute(
            select(Agent).where(
                Agent.id == assign.agent_id,
                Agent.workspace_id == workspace_id,
            )
        )
        agent = agent_result.scalar_one_or_none()

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

    conversation.assigned_agent_id = assign.agent_id
    await db.commit()

    return {"assigned_agent_id": conversation.assigned_agent_id}
