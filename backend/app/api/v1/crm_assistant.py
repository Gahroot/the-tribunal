"""CRM assistant endpoints — operator chat with AI assistant."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.assistant_conversation import AssistantConversation, AssistantMessage
from app.models.workspace import Workspace
from app.schemas.crm_assistant import (
    ActionSummary,
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantConversationResponse,
    AssistantMessageResponse,
)
from app.services.ai.crm_assistant import process_assistant_message

router = APIRouter()


@router.post("/chat", response_model=AssistantChatResponse)
async def chat_with_assistant(
    workspace_id: uuid.UUID,
    request: AssistantChatRequest,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> AssistantChatResponse:
    """Send a message to the CRM assistant and get a response."""
    result = await process_assistant_message(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id,
        message=request.message,
    )
    return AssistantChatResponse(
        response=result["response"],
        actions_taken=[ActionSummary(**a) for a in result["actions_taken"]],
    )


@router.get("/history", response_model=AssistantConversationResponse | None)
async def get_assistant_history(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> AssistantConversationResponse | None:
    """Get conversation history with the CRM assistant."""
    conv_result = await db.execute(
        select(AssistantConversation).where(
            AssistantConversation.workspace_id == workspace_id,
            AssistantConversation.user_id == current_user.id,
        )
    )
    conversation = conv_result.scalar_one_or_none()
    if conversation is None:
        return None

    messages_result = await db.execute(
        select(AssistantMessage)
        .where(AssistantMessage.conversation_id == conversation.id)
        .order_by(AssistantMessage.created_at)
    )
    messages = messages_result.scalars().all()

    return AssistantConversationResponse(
        id=str(conversation.id),
        messages=[
            AssistantMessageResponse(
                id=str(m.id),
                role=m.role,
                content=m.content,
                tool_calls=m.tool_calls,
                tool_call_id=m.tool_call_id,
                created_at=m.created_at,
            )
            for m in messages
        ],
        created_at=conversation.created_at,
    )
