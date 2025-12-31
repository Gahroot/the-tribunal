"""Agent management endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser, get_workspace
from app.models.agent import Agent
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
        query = query.where(Agent.is_active == True)

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
