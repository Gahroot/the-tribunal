"""Conversations and messages endpoints."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, get_workspace
from app.core.config import settings
from app.db.pagination import paginate
from app.models.agent import Agent
from app.models.campaign import CampaignContact
from app.models.conversation import Conversation, Message
from app.models.workspace import Workspace
from app.services.ai.text_agent import generate_followup_message
from app.services.telephony.telnyx import TelnyxSMSService

router = APIRouter()


async def sync_campaign_agent(
    conversation: Conversation,
    db: AsyncSession,
) -> bool:
    """Sync the campaign's agent to the conversation if applicable.

    If the conversation is part of a campaign with an assigned agent,
    ensure the conversation's assigned_agent_id matches the campaign's agent.
    Campaign agent always takes precedence.

    Args:
        conversation: The conversation to sync
        db: Database session

    Returns:
        True if any updates were made, False otherwise
    """
    campaign_contact_result = await db.execute(
        select(CampaignContact)
        .options(selectinload(CampaignContact.campaign))
        .where(CampaignContact.conversation_id == conversation.id)
    )
    campaign_contact = campaign_contact_result.scalar_one_or_none()

    if not campaign_contact or not campaign_contact.campaign:
        return False

    campaign = campaign_contact.campaign
    updated = False

    # Sync agent if campaign has one and it differs from conversation
    if campaign.agent_id and conversation.assigned_agent_id != campaign.agent_id:
        conversation.assigned_agent_id = campaign.agent_id
        updated = True

    # Enable AI if campaign has it enabled and conversation doesn't
    if campaign.ai_enabled and not conversation.ai_enabled:
        conversation.ai_enabled = True
        updated = True

    if updated:
        await db.commit()
        await db.refresh(conversation)

    return updated


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

    model_config = ConfigDict(from_attributes=True)


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

    query = query.order_by(Conversation.last_message_at.desc().nullslast())
    result = await paginate(db, query, page=page, page_size=page_size)
    conversations = list(result.items)

    # Sync campaign agents for all conversations in a single batch query
    if conversations:
        conversation_ids = [c.id for c in conversations]
        campaign_contacts_result = await db.execute(
            select(CampaignContact)
            .options(selectinload(CampaignContact.campaign))
            .where(CampaignContact.conversation_id.in_(conversation_ids))
        )
        campaign_contacts = campaign_contacts_result.scalars().all()

        # Build a map of conversation_id -> campaign
        campaign_by_conv_id = {
            cc.conversation_id: cc.campaign
            for cc in campaign_contacts
            if cc.campaign is not None
        }

        # Sync agents for conversations that are part of campaigns
        needs_commit = False
        for conv in conversations:
            campaign = campaign_by_conv_id.get(conv.id)
            if campaign and campaign.agent_id:
                if conv.assigned_agent_id != campaign.agent_id:
                    conv.assigned_agent_id = campaign.agent_id
                    needs_commit = True
                if campaign.ai_enabled and not conv.ai_enabled:
                    conv.ai_enabled = True
                    needs_commit = True

        if needs_commit:
            await db.commit()
            # Refresh all conversations that were modified
            for conv in conversations:
                await db.refresh(conv)

    return PaginatedConversations(
        items=[ConversationResponse.model_validate(c) for c in conversations],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        pages=result.pages,
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

    # Sync campaign agent if this conversation is part of a campaign
    # Campaign agent always takes precedence over conversation's assigned agent
    await sync_campaign_agent(conversation, db)

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


@router.delete("/{conversation_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_conversation_history(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Clear all messages in a conversation (delete conversation history)."""
    from sqlalchemy import delete

    # Verify conversation exists and belongs to workspace
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

    # Delete all messages in the conversation
    await db.execute(
        delete(Message).where(Message.conversation_id == conversation_id)
    )

    # Reset conversation preview fields
    conversation.last_message_preview = None
    conversation.last_message_at = None
    conversation.last_message_direction = None
    conversation.unread_count = 0

    await db.commit()


# === Follow-up Schemas ===


class FollowupSettingsUpdate(BaseModel):
    """Schema for updating follow-up settings."""

    enabled: bool | None = None
    delay_hours: int | None = Field(None, ge=1, le=168)  # 1 hour to 1 week
    max_count: int | None = Field(None, ge=1, le=10)


class FollowupSettingsResponse(BaseModel):
    """Follow-up settings and status response."""

    enabled: bool
    delay_hours: int
    max_count: int
    count_sent: int
    next_followup_at: datetime | None
    last_followup_at: datetime | None


class FollowupGenerateRequest(BaseModel):
    """Request for generating a follow-up message."""

    custom_instructions: str | None = None


class FollowupGenerateResponse(BaseModel):
    """Response with generated follow-up message."""

    message: str
    conversation_id: str


class FollowupSendRequest(BaseModel):
    """Request for sending a follow-up message."""

    message: str | None = None  # If not provided, will generate one
    custom_instructions: str | None = None


class FollowupSendResponse(BaseModel):
    """Response after sending a follow-up."""

    success: bool
    message_id: str | None
    message_body: str


# === Follow-up Endpoints ===


@router.get("/{conversation_id}/followup/status", response_model=FollowupSettingsResponse)
async def get_followup_status(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> FollowupSettingsResponse:
    """Get follow-up settings and status for a conversation."""
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

    return FollowupSettingsResponse(
        enabled=conversation.followup_enabled,
        delay_hours=conversation.followup_delay_hours,
        max_count=conversation.followup_max_count,
        count_sent=conversation.followup_count_sent,
        next_followup_at=conversation.next_followup_at,
        last_followup_at=conversation.last_followup_at,
    )


@router.patch("/{conversation_id}/followup/settings", response_model=FollowupSettingsResponse)
async def update_followup_settings(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    settings_update: FollowupSettingsUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> FollowupSettingsResponse:
    """Update follow-up settings for a conversation."""
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

    # Update fields if provided
    if settings_update.enabled is not None:
        conversation.followup_enabled = settings_update.enabled
        # If enabling and no next_followup_at is set, schedule one
        if settings_update.enabled and not conversation.next_followup_at:
            conversation.next_followup_at = datetime.now(UTC) + timedelta(
                hours=conversation.followup_delay_hours
            )

    if settings_update.delay_hours is not None:
        conversation.followup_delay_hours = settings_update.delay_hours

    if settings_update.max_count is not None:
        conversation.followup_max_count = settings_update.max_count

    await db.commit()
    await db.refresh(conversation)

    return FollowupSettingsResponse(
        enabled=conversation.followup_enabled,
        delay_hours=conversation.followup_delay_hours,
        max_count=conversation.followup_max_count,
        count_sent=conversation.followup_count_sent,
        next_followup_at=conversation.next_followup_at,
        last_followup_at=conversation.last_followup_at,
    )


@router.post("/{conversation_id}/followup/generate", response_model=FollowupGenerateResponse)
async def generate_followup(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    request: FollowupGenerateRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> FollowupGenerateResponse:
    """Generate a follow-up message preview (does not send)."""
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

    # Check for OpenAI API key
    openai_key = settings.openai_api_key
    if not openai_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )

    # Generate follow-up message
    message = await generate_followup_message(
        conversation=conversation,
        db=db,
        openai_api_key=openai_key,
        custom_instructions=request.custom_instructions,
    )

    if not message:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate follow-up message",
        )

    return FollowupGenerateResponse(
        message=message,
        conversation_id=str(conversation_id),
    )


@router.post("/{conversation_id}/followup/send", response_model=FollowupSendResponse)
async def send_followup(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    request: FollowupSendRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> FollowupSendResponse:
    """Send a follow-up message. Generates one if not provided."""
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

    # Get the message to send
    message_body = request.message
    if not message_body:
        # Generate one
        openai_key = settings.openai_api_key
        if not openai_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service not configured",
            )

        message_body = await generate_followup_message(
            conversation=conversation,
            db=db,
            openai_api_key=openai_key,
            custom_instructions=request.custom_instructions,
        )

        if not message_body:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate follow-up message",
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
            body=message_body,
            db=db,
            workspace_id=workspace_id,
        )

        # Update follow-up tracking
        conversation.followup_count_sent += 1
        conversation.last_followup_at = datetime.now(UTC)

        # Schedule next follow-up if still within limits
        if (
            conversation.followup_enabled
            and conversation.followup_count_sent < conversation.followup_max_count
        ):
            conversation.next_followup_at = datetime.now(UTC) + timedelta(
                hours=conversation.followup_delay_hours
            )
        else:
            conversation.next_followup_at = None

        await db.commit()

        return FollowupSendResponse(
            success=True,
            message_id=str(message.id),
            message_body=message_body,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send message: {str(e)}",
        ) from e
    finally:
        await sms_service.close()


@router.post("/{conversation_id}/followup/reset")
async def reset_followup_counter(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, int]:
    """Reset the follow-up counter to 0."""
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

    conversation.followup_count_sent = 0

    # Re-schedule next follow-up if enabled
    if conversation.followup_enabled:
        conversation.next_followup_at = datetime.now(UTC) + timedelta(
            hours=conversation.followup_delay_hours
        )

    await db.commit()

    return {"count_sent": 0}
