"""Boundary validation for workspace/agent model policy."""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.deps import get_workspace_admin
from app.api.v1.model_configs import ModelPolicyUpdate, _check_agent, router, set_model_policy


@pytest.mark.asyncio
async def test_other_workspace_agent_is_not_addressable() -> None:
    db = SimpleNamespace(scalar=AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as error:
        await _check_agent(db, uuid.uuid4(), uuid.uuid4())
    assert error.value.status_code == 404
    assert "agents.workspace_id" in str(db.scalar.call_args.args[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_scoped", [False, True])
async def test_put_uses_scoped_idempotent_upsert(agent_scoped: bool) -> None:
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=uuid.uuid4()),
        execute=AsyncMock(),
        commit=AsyncMock(),
    )
    agent_id = uuid.uuid4() if agent_scoped else None
    policy = ModelPolicyUpdate(model="gpt-5.4-mini")
    response = await set_model_policy(uuid.uuid4(), "reports", policy, None, db, None, agent_id)
    assert response.model == policy.model
    db.commit.assert_awaited_once()
    sql = str(db.execute.call_args.args[0].compile())
    assert "ON CONFLICT" in sql
    assert "agent_id IS NOT NULL" in sql if agent_scoped else "agent_id IS NULL" in sql


def test_policy_writes_require_workspace_admin() -> None:
    writes = [route for route in router.routes if route.methods & {"PUT", "DELETE"}]
    assert len(writes) == 2
    for route in writes:
        assert any(dep.call is get_workspace_admin for dep in route.dependant.dependencies)


def test_pricing_requires_both_rates() -> None:
    with pytest.raises(ValidationError):
        ModelPolicyUpdate(model="gpt-5.4-mini", input_usd_per_million=Decimal("1"))
    with pytest.raises(ValidationError):
        ModelPolicyUpdate(model="gpt-5.4-mini", output_usd_per_million=Decimal("-1"))
