"""Workspace/agent model policy for production AI tasks."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import DB, CurrentUser, get_workspace, get_workspace_admin
from app.models.agent import Agent
from app.models.model_config import ModelConfig
from app.models.workspace import Workspace
from app.services.ai.model_config import DEFAULTS, Selection, Task, resolve_model
from app.services.ai.openai_realtime_config import normalize_realtime_model

router = APIRouter()


class ModelPolicyUpdate(BaseModel):
    model: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    input_usd_per_million: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=6
    )
    output_usd_per_million: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=6
    )

    @model_validator(mode="after")
    def prices_together(self) -> "ModelPolicyUpdate":
        if (self.input_usd_per_million is None) != (self.output_usd_per_million is None):
            raise ValueError("Both input and output prices must be provided together")
        return self


class ModelPolicyResponse(BaseModel):
    task: Task
    model: str
    input_usd_per_million: Decimal | None
    output_usd_per_million: Decimal | None


def _response(task: Task, selection: Selection) -> ModelPolicyResponse:
    return ModelPolicyResponse(
        task=task,
        model=selection.model,
        input_usd_per_million=selection.input_usd_per_million,
        output_usd_per_million=selection.output_usd_per_million,
    )


async def _check_agent(db: DB, workspace_id: uuid.UUID, agent_id: uuid.UUID | None) -> None:
    if (
        agent_id is not None
        and (
            await db.scalar(
                select(Agent.id).where(Agent.workspace_id == workspace_id, Agent.id == agent_id)
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Agent not found")


@router.get("", response_model=list[ModelPolicyResponse])
async def list_model_policies(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
    agent_id: uuid.UUID | None = None,
) -> list[ModelPolicyResponse]:
    await _check_agent(db, workspace_id, agent_id)
    return [
        _response(task, await resolve_model(db, task, workspace_id, agent_id)) for task in DEFAULTS
    ]


@router.put("/{task}", response_model=ModelPolicyResponse)
async def set_model_policy(
    workspace_id: uuid.UUID,
    task: Task,
    payload: ModelPolicyUpdate,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace_admin)],
    agent_id: uuid.UUID | None = None,
) -> ModelPolicyResponse:
    await _check_agent(db, workspace_id, agent_id)
    if task == "voice_llm":
        if normalize_realtime_model(payload.model) != payload.model or len(payload.model) > 60:
            raise HTTPException(status_code=422, detail="Unsupported Realtime model")
    elif not payload.model.startswith("gpt-"):
        raise HTTPException(status_code=422, detail="Only OpenAI GPT chat models are supported")
    # The partial unique index is the arbiter; concurrent retries update the same row.
    statement = insert(ModelConfig).values(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        agent_id=agent_id,
        task=task,
        model=payload.model,
        input_usd_per_million=payload.input_usd_per_million,
        output_usd_per_million=payload.output_usd_per_million,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[ModelConfig.agent_id, ModelConfig.task]
        if agent_id
        else [ModelConfig.workspace_id, ModelConfig.task],
        index_where=ModelConfig.agent_id.is_not(None)
        if agent_id
        else ModelConfig.agent_id.is_(None),
        set_={
            "model": payload.model,
            "input_usd_per_million": payload.input_usd_per_million,
            "output_usd_per_million": payload.output_usd_per_million,
        },
    )
    await db.execute(statement)
    if task == "voice_llm" and agent_id is not None:
        agent = await db.scalar(
            select(Agent).where(Agent.workspace_id == workspace_id, Agent.id == agent_id)
        )
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent.realtime_model = payload.model
    await db.commit()
    return _response(
        task,
        Selection(payload.model, payload.input_usd_per_million, payload.output_usd_per_million),
    )


@router.delete("/{task}", status_code=204)
async def clear_model_policy(
    workspace_id: uuid.UUID,
    task: Task,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace_admin)],
    agent_id: uuid.UUID | None = None,
) -> None:
    await _check_agent(db, workspace_id, agent_id)
    row = (
        await db.execute(
            select(ModelConfig).where(
                ModelConfig.workspace_id == workspace_id,
                ModelConfig.task == task,
                ModelConfig.agent_id == agent_id if agent_id else ModelConfig.agent_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
    if task == "voice_llm" and agent_id is not None:
        agent = await db.scalar(
            select(Agent).where(Agent.workspace_id == workspace_id, Agent.id == agent_id)
        )
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent.realtime_model = None
    await db.commit()
