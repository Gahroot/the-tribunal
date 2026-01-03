"""Voice call management endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.core.config import settings
from app.models.conversation import Message
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
    created_at: datetime

    class Config:
        from_attributes = True


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

    if not settings.telnyx_connection_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telnyx connection ID not configured",
        )

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
        # Build webhook URL
        webhook_url = f"{settings.api_base_url or 'https://example.com'}/webhooks/telnyx/voice"

        message = await voice_service.initiate_call(
            to_number=call_data.to_number,
            from_number=call_data.from_phone_number,
            connection_id=settings.telnyx_connection_id,
            webhook_url=webhook_url,
            db=db,
            workspace_id=workspace_id,
            contact_phone=call_data.contact_phone,
            agent_id=call_data.agent_id,
        )

        return CallResponse.model_validate(message)
    finally:
        await voice_service.close()


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
    # Query voice messages (calls)
    query = select(Message).where(
        Message.channel == "voice",
    )

    # Filter by conversations in this workspace
    from app.models.conversation import Conversation

    conv_query = select(Conversation.id).where(
        Conversation.workspace_id == workspace_id
    )
    query = query.where(Message.conversation_id.in_(conv_query.subquery()))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(Message.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    messages = result.scalars().all()

    return PaginatedCalls(
        items=[CallResponse.model_validate(m) for m in messages],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
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

    return CallResponse.model_validate(message)


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
