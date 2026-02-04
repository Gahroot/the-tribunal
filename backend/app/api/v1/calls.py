"""Voice call management endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_workspace
from app.core.config import settings
from app.db.pagination import paginate_unique
from app.models.conversation import Conversation, Message
from app.models.phone_number import PhoneNumber
from app.models.workspace import Workspace
from app.services.telephony.telnyx_voice import TelnyxVoiceService

router = APIRouter()


class CallCreate(BaseModel):
    """Request to initiate a call."""

    to_number: str
    from_phone_number: str
    contact_phone: str | None = None
    agent_id: uuid.UUID | None = None


class CallResponse(BaseModel):
    """Voice call response."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    direction: str  # inbound/outbound
    channel: str
    status: str  # queued/ringing/answered/completed/failed
    duration_seconds: int | None
    recording_url: str | None
    transcript: str | None  # JSON array of transcript entries
    created_at: datetime
    # Phone numbers from conversation
    from_number: str | None = None
    to_number: str | None = None
    # Agent info
    agent_id: uuid.UUID | None = None
    agent_name: str | None = None
    is_ai: bool = False


class PaginatedCalls(BaseModel):
    """Paginated calls response."""

    items: list[CallResponse]
    total: int
    page: int
    page_size: int
    pages: int


@router.post("", response_model=CallResponse, status_code=status.HTTP_201_CREATED)
async def initiate_call(
    workspace_id: uuid.UUID,
    call_data: CallCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> CallResponse:
    """Initiate outbound voice call.

    Args:
        workspace_id: Workspace ID
        call_data: Call request data
        current_user: Current user
        db: Database session
        workspace: Workspace object

    Returns:
        Created Message record for the call
    """
    if not settings.telnyx_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telnyx not configured",
        )

    # Note: telnyx_connection_id is optional - the service auto-discovers
    # a Call Control Application ID if not provided

    # Verify the from_phone_number belongs to workspace
    result = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.workspace_id == workspace_id,
            PhoneNumber.phone_number == call_data.from_phone_number,
            PhoneNumber.voice_enabled.is_(True),
        )
    )
    phone_record = result.scalar_one_or_none()

    if not phone_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number not found or voice not enabled",
        )

    # Initiate call via Telnyx
    voice_service = TelnyxVoiceService(settings.telnyx_api_key)
    try:
        # Build webhook URL for call events
        api_base = settings.api_base_url or "https://example.com"
        webhook_url = f"{api_base}/webhooks/telnyx/voice"

        # Connection ID is optional - service auto-discovers if not provided
        connection_id = settings.telnyx_connection_id if settings.telnyx_connection_id else None

        message = await voice_service.initiate_call(
            to_number=call_data.to_number,
            from_number=call_data.from_phone_number,
            connection_id=connection_id,
            webhook_url=webhook_url,
            db=db,
            workspace_id=workspace_id,
            contact_phone=call_data.contact_phone,
            agent_id=call_data.agent_id,
        )

        return CallResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            direction=message.direction,
            channel=message.channel,
            status=message.status,
            duration_seconds=message.duration_seconds,
            recording_url=message.recording_url,
            transcript=message.transcript,
            created_at=message.created_at,
            from_number=call_data.from_phone_number,
            to_number=call_data.to_number,
            agent_id=message.agent_id,
            is_ai=message.is_ai,
        )
    finally:
        await voice_service.close()


def _build_call_response(
    message: Message,
    conversation: Conversation,
    agent_name: str | None = None,
) -> CallResponse:
    """Build CallResponse with phone numbers from conversation."""
    # Determine from/to based on direction
    if message.direction == "outbound":
        from_number = conversation.workspace_phone
        to_number = conversation.contact_phone
    else:
        from_number = conversation.contact_phone
        to_number = conversation.workspace_phone

    return CallResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        direction=message.direction,
        channel=message.channel,
        status=message.status,
        duration_seconds=message.duration_seconds,
        recording_url=message.recording_url,
        transcript=message.transcript,
        created_at=message.created_at,
        from_number=from_number,
        to_number=to_number,
        agent_id=message.agent_id,
        agent_name=agent_name,
        is_ai=message.is_ai,
    )


@router.get("", response_model=PaginatedCalls)
async def list_calls(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> PaginatedCalls:
    """List call history in workspace.

    Args:
        workspace_id: Workspace ID
        current_user: Current user
        db: Database session
        workspace: Workspace object
        page: Page number
        page_size: Items per page

    Returns:
        Paginated list of calls
    """
    from sqlalchemy.orm import joinedload

    # Query voice messages with their conversations and agents
    query = (
        select(Message)
        .options(joinedload(Message.conversation), joinedload(Message.agent))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Message.channel == "voice",
            Conversation.workspace_id == workspace_id,
        )
    )

    query = query.order_by(Message.created_at.desc())
    result = await paginate_unique(db, query, page=page, page_size=page_size)

    return PaginatedCalls(
        items=[
            _build_call_response(
                m, m.conversation, agent_name=m.agent.name if m.agent else None
            )
            for m in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        pages=result.pages,
    )


@router.get("/{call_id}", response_model=CallResponse)
async def get_call(
    workspace_id: uuid.UUID,
    call_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> CallResponse:
    """Get call details with recording and transcript.

    Args:
        workspace_id: Workspace ID
        call_id: Call (Message) ID
        current_user: Current user
        db: Database session
        workspace: Workspace object

    Returns:
        Message record with call details
    """
    from sqlalchemy.orm import joinedload

    # Get the message with conversation and agent
    result = await db.execute(
        select(Message)
        .options(joinedload(Message.conversation), joinedload(Message.agent))
        .where(
            Message.id == call_id,
            Message.channel == "voice",
        )
    )
    message = result.unique().scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found",
        )

    # Verify workspace access
    if message.conversation.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return _build_call_response(
        message, message.conversation, agent_name=message.agent.name if message.agent else None
    )


@router.post("/{call_id}/hangup")
async def hangup_call(
    workspace_id: uuid.UUID,
    call_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, bool]:
    """Hang up active call.

    Args:
        workspace_id: Workspace ID
        call_id: Call (Message) ID
        current_user: Current user
        db: Database session
        workspace: Workspace object

    Returns:
        Success status
    """
    if not settings.telnyx_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telnyx not configured",
        )

    # Get the message
    result = await db.execute(
        select(Message).where(
            Message.id == call_id,
            Message.channel == "voice",
        )
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found",
        )

    # Verify workspace access
    from app.models.conversation import Conversation

    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == message.conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    )

    if not conv_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Hangup via Telnyx
    if not message.provider_message_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Call does not have a provider message ID",
        )

    voice_service = TelnyxVoiceService(settings.telnyx_api_key)
    try:
        success = await voice_service.hangup_call(message.provider_message_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to hangup call",
            )

        return {"success": True}
    finally:
        await voice_service.close()
