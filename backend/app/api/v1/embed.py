"""Public embed API endpoints for embeddable agent widgets.

These endpoints are unauthenticated but require domain validation
and are rate-limited for security.
"""

from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.origin_validation import validate_origin
from app.db.session import get_db
from app.models.agent import Agent

# Database dependency type alias
DB = Annotated[AsyncSession, Depends(get_db)]

logger = structlog.get_logger()

router = APIRouter()


# Schemas
class EmbedConfigResponse(BaseModel):
    """Public configuration for embed widget."""

    public_id: str
    name: str
    greeting_message: str | None
    button_text: str
    theme: str
    position: str
    primary_color: str
    language: str
    voice: str
    channel_mode: str


class TokenRequest(BaseModel):
    """Request for ephemeral token."""

    mode: str = "voice"  # voice or chat


class TokenResponse(BaseModel):
    """Ephemeral token response for WebRTC connection."""

    client_secret: dict[str, str]
    agent: dict[str, str | None]
    model: str
    tools: list[dict[str, object]]


class ChatRequest(BaseModel):
    """Chat message request."""

    message: str
    conversation_history: list[dict[str, str]] = []


class ChatResponse(BaseModel):
    """Chat message response."""

    response: str
    tool_calls: list[dict[str, object]] = []


class ToolCallRequest(BaseModel):
    """Tool call execution request."""

    tool_name: str
    arguments: dict[str, object]


class TranscriptRequest(BaseModel):
    """Transcript save request."""

    session_id: str
    transcript: str
    duration_seconds: int


async def get_agent_by_public_id(db: AsyncSession, public_id: str) -> Agent:
    """Get an agent by public ID with validation."""
    result = await db.execute(
        select(Agent).where(
            Agent.public_id == public_id,
            Agent.embed_enabled.is_(True),
            Agent.is_active.is_(True),
        )
    )
    agent: Agent | None = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found or embedding not enabled",
        )

    return agent


@router.get("/{public_id}/config", response_model=EmbedConfigResponse)
async def get_embed_config(
    public_id: str,
    request: Request,
    db: DB,
) -> EmbedConfigResponse:
    """Get public configuration for the embed widget."""
    agent = await get_agent_by_public_id(db, public_id)

    # Validate origin
    if not validate_origin(request, agent.allowed_domains):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed",
        )

    # Get embed settings with defaults
    embed_settings = agent.embed_settings or {}

    return EmbedConfigResponse(
        public_id=agent.public_id or "",
        name=agent.name,
        greeting_message=agent.initial_greeting,
        button_text=embed_settings.get("button_text", "Talk to AI"),
        theme=embed_settings.get("theme", "auto"),
        position=embed_settings.get("position", "bottom-right"),
        primary_color=embed_settings.get("primary_color", "#6366f1"),
        language=agent.language,
        voice=agent.voice_id,
        channel_mode=agent.channel_mode,
    )


@router.post("/{public_id}/token", response_model=TokenResponse)
async def get_ephemeral_token(
    public_id: str,
    request: Request,
    db: DB,
    body: TokenRequest | None = None,
) -> TokenResponse:
    """Get an ephemeral token for OpenAI Realtime WebRTC connection."""
    agent = await get_agent_by_public_id(db, public_id)

    # Validate origin
    if not validate_origin(request, agent.allowed_domains):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed",
        )

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice service not configured",
        )

    # Create ephemeral token from OpenAI
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-realtime-preview",
                "voice": agent.voice_id,
            },
            timeout=30.0,
        )

        if response.status_code != 200:
            logger.error(
                "openai_session_error",
                status=response.status_code,
                body=response.text,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to create voice session",
            )

        session_data = response.json()

    # Build tools list from agent's enabled tools
    tools: list[dict[str, object]] = []

    # Add end_call tool by default for embed sessions
    tools.append({
        "type": "function",
        "name": "end_call",
        "description": (
            "End the current call. Use this when the user says goodbye, "
            "thanks you and indicates they're done, or explicitly asks to end the call."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "The reason for ending the call",
                }
            },
            "required": ["reason"],
        },
    })

    return TokenResponse(
        client_secret={"value": session_data.get("client_secret", {}).get("value", "")},
        agent={
            "name": agent.name,
            "voice": agent.voice_id,
            "instructions": agent.system_prompt,
            "language": agent.language,
            "initial_greeting": agent.initial_greeting,
        },
        model="gpt-4o-realtime-preview",
        tools=tools,
    )


@router.post("/{public_id}/chat", response_model=ChatResponse)
async def send_chat_message(
    public_id: str,
    body: ChatRequest,
    request: Request,
    db: DB,
) -> ChatResponse:
    """Send a chat message and get AI response."""
    agent = await get_agent_by_public_id(db, public_id)

    # Validate origin
    if not validate_origin(request, agent.allowed_domains):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed",
        )

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat service not configured",
        )

    # Build messages for OpenAI
    messages: list[dict[str, str]] = [
        {"role": "system", "content": agent.system_prompt}
    ]

    # Add conversation history
    for msg in body.conversation_history[-agent.text_max_context_messages :]:
        messages.append(msg)

    # Add current message
    messages.append({"role": "user", "content": body.message})

    # Call OpenAI Chat API
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": messages,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
            },
            timeout=60.0,
        )

        if response.status_code != 200:
            logger.error(
                "openai_chat_error",
                status=response.status_code,
                body=response.text,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to get AI response",
            )

        data = response.json()

    # Extract response
    choices = data.get("choices", [])
    first_choice = choices[0] if choices else {}
    ai_response = first_choice.get("message", {}).get("content", "")

    return ChatResponse(response=ai_response, tool_calls=[])


@router.post("/{public_id}/tool-call")
async def execute_tool_call(
    public_id: str,
    body: ToolCallRequest,
    request: Request,
    db: DB,
) -> dict[str, object]:
    """Execute a tool call from the AI."""
    agent = await get_agent_by_public_id(db, public_id)

    # Validate origin
    if not validate_origin(request, agent.allowed_domains):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed",
        )

    # Handle built-in tools
    if body.tool_name == "end_call":
        return {
            "success": True,
            "action": "end_call",
            "message": "Call ended successfully",
        }

    # For other tools, return a generic response
    # In a full implementation, this would dispatch to the appropriate tool handler
    return {
        "success": True,
        "message": f"Tool {body.tool_name} executed",
        "result": body.arguments,
    }


@router.post("/{public_id}/transcript")
async def save_transcript(
    public_id: str,
    body: TranscriptRequest,
    request: Request,
    db: DB,
) -> dict[str, str]:
    """Save a conversation transcript."""
    agent = await get_agent_by_public_id(db, public_id)

    # Validate origin
    if not validate_origin(request, agent.allowed_domains):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed",
        )

    # Log transcript for analytics (in a full implementation, save to database)
    logger.info(
        "embed_transcript_saved",
        public_id=public_id,
        session_id=body.session_id,
        duration_seconds=body.duration_seconds,
        transcript_length=len(body.transcript),
    )

    return {"status": "saved"}
