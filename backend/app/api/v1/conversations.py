"""Conversations and messages endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.conversation import Message
from app.models.workspace import Workspace
from app.schemas.conversation import (
    AgentAssign,
    AIToggle,
    ConversationWithMessages,
    FollowupGenerateRequest,
    FollowupGenerateResponse,
    FollowupSendRequest,
    FollowupSendResponse,
    FollowupSettingsResponse,
    FollowupSettingsUpdate,
    InboxConversationResponse,
    InboxMessageResponse,
    InboxSearch,
    InboxView,
    MarkConversationRead,
    MarkConversationReadResponse,
    MessageCreate,
    MessageResponse,
    PaginatedConversations,
    PaginatedInbox,
)
from app.schemas.message_trace import MessageTraceResponse
from app.services.conversations import ConversationService
from app.services.outbound.message_trace import message_trace_service

router = APIRouter()


@router.get(
    "/messages/{message_id}/trace",
    response_model=MessageTraceResponse,
)
async def get_message_trace(
    workspace_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> MessageTraceResponse:
    """Fetch the decision/trace for one autonomously-sent message.

    Answers "why did the agent send that?" — returns the opener/prompt version,
    retrieved knowledge snippets, model params, conversation state plus last
    inbound, and which autonomy-mandate rule authorized the send.
    """
    trace = await message_trace_service.get_by_message(
        db, workspace_id=workspace_id, message_id=message_id
    )
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No trace recorded for this message",
        )
    return MessageTraceResponse.model_validate(trace)


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
    svc = ConversationService(db)
    return await svc.list_conversations(
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        channel_filter=channel_filter,
        unread_only=unread_only,
    )


@router.get("/inbox", response_model=PaginatedInbox)
async def list_inbox(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    view: InboxView = "all",
    q: str = Query("", max_length=200),
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(50, ge=1, le=100),
) -> PaginatedInbox:
    """Read-only conversation discovery with search-relative view counts."""
    return await ConversationService(db).list_inbox(workspace_id, view, q, page, page_size)


@router.post("/inbox/search", response_model=PaginatedInbox)
async def search_inbox(
    workspace_id: uuid.UUID,
    request: InboxSearch,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> PaginatedInbox:
    """Read-only search with no operator-entered text in the request URL."""
    return await ConversationService(db).list_inbox(
        workspace_id, request.view, request.q, request.page, request.page_size
    )


@router.get("/{conversation_id}/inbox-detail", response_model=InboxConversationResponse)
async def get_inbox_conversation(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> InboxConversationResponse:
    """Fetch selected thread metadata without marking read or synchronizing AI."""
    return await ConversationService(db).get_inbox_conversation(conversation_id, workspace_id)


@router.post("/{conversation_id}/read", response_model=MarkConversationReadResponse)
async def mark_conversation_read(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    request: MarkConversationRead,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> MarkConversationReadResponse:
    """Acknowledge a displayed snapshot; leave newer arrivals unread."""
    return await ConversationService(db).mark_read(
        conversation_id, workspace_id, request.last_message_at, request.unread_count
    )


@router.get(
    "/{conversation_id}/traces",
    response_model=list[MessageTraceResponse],
)
async def list_conversation_traces(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    limit: int = Query(100, ge=1, le=500),
) -> list[MessageTraceResponse]:
    """List decision/traces for every autonomous message in a conversation."""
    traces = await message_trace_service.list_by_conversation(
        db,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        limit=limit,
    )
    return [MessageTraceResponse.model_validate(trace) for trace in traces]


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
    svc = ConversationService(db)
    return await svc.get_conversation(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        limit=limit,
    )


@router.get("/{conversation_id}/messages", response_model=list[InboxMessageResponse])
async def list_conversation_messages(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    limit: int = Query(100, ge=1, le=200),
) -> list[Message]:
    """Read recent messages, oldest first, without changing AI ownership."""
    return await ConversationService(db).list_messages(conversation_id, workspace_id, limit)


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
    svc = ConversationService(db)
    return await svc.send_message(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        body=message_in.body,
    )


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
    svc = ConversationService(db)
    return await svc.toggle_ai(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        enabled=toggle.enabled,
    )


@router.post("/{conversation_id}/ai/pause")
async def pause_ai(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, bool]:
    """Pause AI for a conversation (temporary)."""
    svc = ConversationService(db)
    return await svc.pause_ai(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
    )


@router.post("/{conversation_id}/ai/resume")
async def resume_ai(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, bool]:
    """Resume AI for a conversation."""
    svc = ConversationService(db)
    return await svc.resume_ai(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
    )


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
    svc = ConversationService(db)
    return await svc.assign_agent(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        agent_id=assign.agent_id,
    )


@router.delete("/{conversation_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_conversation_history(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Clear all messages in a conversation."""
    svc = ConversationService(db)
    await svc.clear_history(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
    )


@router.get(
    "/{conversation_id}/followup/status",
    response_model=FollowupSettingsResponse,
)
async def get_followup_status(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> FollowupSettingsResponse:
    """Get follow-up settings and status for a conversation."""
    svc = ConversationService(db)
    return await svc.get_followup_status(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
    )


@router.patch(
    "/{conversation_id}/followup/settings",
    response_model=FollowupSettingsResponse,
)
async def update_followup_settings(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    settings_update: FollowupSettingsUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> FollowupSettingsResponse:
    """Update follow-up settings for a conversation."""
    svc = ConversationService(db)
    return await svc.update_followup_settings(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        enabled=settings_update.enabled,
        delay_hours=settings_update.delay_hours,
        max_count=settings_update.max_count,
    )


@router.post(
    "/{conversation_id}/followup/generate",
    response_model=FollowupGenerateResponse,
)
async def generate_followup(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    request: FollowupGenerateRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> FollowupGenerateResponse:
    """Generate a follow-up message preview (does not send)."""
    svc = ConversationService(db)
    return await svc.generate_followup(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        custom_instructions=request.custom_instructions,
    )


@router.post(
    "/{conversation_id}/followup/send",
    response_model=FollowupSendResponse,
)
async def send_followup(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    request: FollowupSendRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> FollowupSendResponse:
    """Send a follow-up message. Generates one if not provided."""
    svc = ConversationService(db)
    return await svc.send_followup(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        message=request.message,
        custom_instructions=request.custom_instructions,
    )


@router.post("/{conversation_id}/followup/reset")
async def reset_followup_counter(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, int]:
    """Reset the follow-up counter to 0."""
    svc = ConversationService(db)
    return await svc.reset_followup_counter(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
    )
