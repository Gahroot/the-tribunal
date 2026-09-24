"""Task model policy resolution and per-call cost accounting."""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.model_config import ModelConfig
from app.services.ai.model_config import DEFAULTS, Selection, log_model_usage, resolve_model


@pytest.mark.asyncio
async def test_agent_override_then_workspace_then_default() -> None:
    workspace = uuid.uuid4()
    agent = uuid.uuid4()
    other_agent = uuid.uuid4()
    rows = [
        ModelConfig(workspace_id=workspace, task="reports", model="gpt-workspace"),
        ModelConfig(workspace_id=workspace, agent_id=agent, task="reports", model="gpt-agent"),
    ]
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    assert (await resolve_model(db, "reports", workspace, agent)).model == "gpt-agent"
    assert (await resolve_model(db, "reports", workspace, other_agent)).model == "gpt-workspace"
    assert (await resolve_model(db, "reports", workspace)).model == "gpt-workspace"
    db.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    assert (await resolve_model(db, "reports", workspace)).model == DEFAULTS["reports"]
    statement = db.execute.call_args.args[0]
    assert "model_configs.workspace_id" in str(statement)


@pytest.mark.asyncio
async def test_unsupported_legacy_voice_override_falls_back_to_workspace() -> None:
    workspace, agent = uuid.uuid4(), uuid.uuid4()
    rows = [
        ModelConfig(workspace_id=workspace, task="voice_llm", model="gpt-realtime-2"),
        ModelConfig(workspace_id=workspace, agent_id=agent, task="voice_llm", model="obsolete"),
    ]
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))
        )
    )
    assert (await resolve_model(db, "voice_llm", workspace, agent)).model == "gpt-realtime-2"


def test_cost_is_null_without_pricing_and_computed_with_pricing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = []
    monkeypatch.setattr(
        "app.services.ai.model_config.structlog.get_logger",
        lambda: SimpleNamespace(info=lambda *args, **kwargs: events.append(kwargs)),
    )
    response = SimpleNamespace(
        model="gpt-test", usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=2000)
    )
    log_model_usage("reports", Selection("gpt-test"), response)
    assert events[-1]["cost_usd"] is None
    log_model_usage("reports", Selection("gpt-test", Decimal("1"), Decimal("2")), response)
    assert events[-1]["cost_usd"] == "0.005"
    assert events[-1]["model"] == "gpt-test"
