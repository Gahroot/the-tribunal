"""Agent management endpoints."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.agent import Agent, generate_public_id
from app.models.workspace import Workspace

router = APIRouter()


# Schemas
class AgentCreate(BaseModel):
    """Schema for creating an agent."""

    name: str
    description: str | None = None
    channel_mode: str = "both"  # voice, text, both
    voice_provider: str = "openai"  # openai, elevenlabs
    voice_id: str = "alloy"
    language: str = "en-US"
    system_prompt: str
    temperature: float = 0.7
    text_response_delay_ms: int = 2000
    text_max_context_messages: int = 20
    calcom_event_type_id: int | None = None
    enabled_tools: list[str] = []
    tool_settings: dict[str, list[str]] = {}


class AgentUpdate(BaseModel):
    """Schema for updating an agent."""

    name: str | None = None
    description: str | None = None
    channel_mode: str | None = None
    voice_provider: str | None = None
    voice_id: str | None = None
    language: str | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    text_response_delay_ms: int | None = None
    text_max_context_messages: int | None = None
    calcom_event_type_id: int | None = None
    is_active: bool | None = None
    enabled_tools: list[str] | None = None
    tool_settings: dict[str, list[str]] | None = None


class AgentResponse(BaseModel):
    """Agent response schema."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    channel_mode: str
    voice_provider: str
    voice_id: str
    language: str
    system_prompt: str
    temperature: float
    text_response_delay_ms: int
    text_max_context_messages: int
    calcom_event_type_id: int | None
    enabled_tools: list[str]
    tool_settings: dict[str, list[str]]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedAgents(BaseModel):
    """Paginated agents response."""

    items: list[AgentResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Endpoints
@router.get("", response_model=PaginatedAgents)
async def list_agents(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    active_only: bool = True,
) -> PaginatedAgents:
    """List agents in a workspace."""
    query = select(Agent).where(Agent.workspace_id == workspace_id)

    if active_only:
        query = query.where(Agent.is_active.is_(True))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Get paginated results
    query = query.order_by(Agent.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    agents = result.scalars().all()

    return PaginatedAgents(
        items=[AgentResponse.model_validate(a) for a in agents],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    workspace_id: uuid.UUID,
    agent_in: AgentCreate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Agent:
    """Create a new agent."""
    agent = Agent(
        workspace_id=workspace_id,
        name=agent_in.name,
        description=agent_in.description,
        channel_mode=agent_in.channel_mode,
        voice_provider=agent_in.voice_provider,
        voice_id=agent_in.voice_id,
        language=agent_in.language,
        system_prompt=agent_in.system_prompt,
        temperature=agent_in.temperature,
        text_response_delay_ms=agent_in.text_response_delay_ms,
        text_max_context_messages=agent_in.text_max_context_messages,
        calcom_event_type_id=agent_in.calcom_event_type_id,
        enabled_tools=agent_in.enabled_tools,
        tool_settings=agent_in.tool_settings,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    return agent


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Agent:
    """Get an agent by ID."""
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.workspace_id == workspace_id,
        )
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    agent_in: AgentUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> Agent:
    """Update an agent."""
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.workspace_id == workspace_id,
        )
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    # Update fields
    update_data = agent_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)

    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> None:
    """Delete an agent (soft delete by deactivating)."""
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.workspace_id == workspace_id,
        )
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    agent.is_active = False
    await db.commit()


# Embed settings schemas
class EmbedSettings(BaseModel):
    """Embed widget settings."""

    button_text: str = "Talk to AI"
    theme: str = "auto"  # auto, light, dark
    position: str = "bottom-right"  # bottom-right, bottom-left, top-right, top-left
    primary_color: str = "#6366f1"
    mode: str = "voice"  # voice, chat, both


class EmbedSettingsResponse(BaseModel):
    """Response for embed settings."""

    public_id: str | None
    embed_enabled: bool
    allowed_domains: list[str]
    embed_settings: EmbedSettings
    embed_code: str | None


class EmbedSettingsUpdate(BaseModel):
    """Request to update embed settings."""

    embed_enabled: bool | None = None
    allowed_domains: list[str] | None = None
    embed_settings: dict[str, Any] | None = None


@router.get("/{agent_id}/embed", response_model=EmbedSettingsResponse)
async def get_embed_settings(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> EmbedSettingsResponse:
    """Get embed settings for an agent."""
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.workspace_id == workspace_id,
        )
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    # Generate public ID if not exists
    if not agent.public_id:
        agent.public_id = generate_public_id()
        await db.commit()
        await db.refresh(agent)

    # Build embed code snippet
    embed_settings = agent.embed_settings or {}
    mode = embed_settings.get("mode", "voice")
    embed_code = None

    if agent.embed_enabled and agent.public_id:
        # Use relative URL - frontend will determine the base URL
        embed_code = f'''<script src="/widget/v1/widget.js" defer></script>
<ai-agent agent-id="{agent.public_id}" mode="{mode}"></ai-agent>'''

    return EmbedSettingsResponse(
        public_id=agent.public_id,
        embed_enabled=agent.embed_enabled,
        allowed_domains=agent.allowed_domains or [],
        embed_settings=EmbedSettings(**{
            "button_text": embed_settings.get("button_text", "Talk to AI"),
            "theme": embed_settings.get("theme", "auto"),
            "position": embed_settings.get("position", "bottom-right"),
            "primary_color": embed_settings.get("primary_color", "#6366f1"),
            "mode": embed_settings.get("mode", "voice"),
        }),
        embed_code=embed_code,
    )


@router.put("/{agent_id}/embed", response_model=EmbedSettingsResponse)
async def update_embed_settings(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: EmbedSettingsUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> EmbedSettingsResponse:
    """Update embed settings for an agent."""
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.workspace_id == workspace_id,
        )
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    # Generate public ID if enabling embed and none exists
    if body.embed_enabled and not agent.public_id:
        agent.public_id = generate_public_id()

    # Update fields
    if body.embed_enabled is not None:
        agent.embed_enabled = body.embed_enabled

    if body.allowed_domains is not None:
        agent.allowed_domains = body.allowed_domains

    if body.embed_settings is not None:
        # Merge with existing settings
        current_settings = agent.embed_settings or {}
        current_settings.update(body.embed_settings)
        agent.embed_settings = current_settings

    await db.commit()
    await db.refresh(agent)

    # Build embed code snippet
    embed_settings = agent.embed_settings or {}
    mode = embed_settings.get("mode", "voice")
    embed_code = None

    if agent.embed_enabled and agent.public_id:
        embed_code = f'''<script src="/widget/v1/widget.js" defer></script>
<ai-agent agent-id="{agent.public_id}" mode="{mode}"></ai-agent>'''

    return EmbedSettingsResponse(
        public_id=agent.public_id,
        embed_enabled=agent.embed_enabled,
        allowed_domains=agent.allowed_domains or [],
        embed_settings=EmbedSettings(**{
            "button_text": embed_settings.get("button_text", "Talk to AI"),
            "theme": embed_settings.get("theme", "auto"),
            "position": embed_settings.get("position", "bottom-right"),
            "primary_color": embed_settings.get("primary_color", "#6366f1"),
            "mode": embed_settings.get("mode", "voice"),
        }),
        embed_code=embed_code,
    )
