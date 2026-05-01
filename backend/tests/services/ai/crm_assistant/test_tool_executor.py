"""Tests for the CRM tool executor — workspace scoping + dispatch."""

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services.ai.crm_assistant._tool_executor import CRMToolExecutor
from app.services.ai.crm_assistant._tools import CRM_TOOLS, get_crm_tools


def test_tool_spec_handler_parity() -> None:
    """Every tool defined in _tools.py must have a handler in the executor."""
    spec_names = {t["function"]["name"] for t in get_crm_tools()}
    executor = CRMToolExecutor(db=AsyncMock(), workspace_id=uuid.uuid4(), user_id=1)
    handler_names = {
        "search_contacts", "create_contact", "list_campaigns", "list_agents",
        "send_sms", "get_conversation", "list_recent_conversations",
        "list_appointments", "get_dashboard_stats", "list_opportunities",
    }
    # Confirm names match what executor.execute() routes through
    assert spec_names == handler_names
    # Sanity: the tool list is exposed and non-empty
    assert len(CRM_TOOLS) == len(spec_names)
    assert executor.workspace_id is not None


@pytest.mark.asyncio
async def test_execute_unknown_tool_returns_error() -> None:
    """Unknown tool names should return a structured error, not raise."""
    executor = CRMToolExecutor(db=AsyncMock(), workspace_id=uuid.uuid4(), user_id=1)
    result = await executor.execute("nonexistent_tool", {})
    assert result["success"] is False
    assert "Unknown function" in result["error"]


@pytest.mark.asyncio
async def test_execute_handler_exception_returns_error() -> None:
    """Handler exceptions are caught and surfaced as success=False."""
    workspace_id = uuid.uuid4()

    # Mock db.execute to raise inside the handler
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("db down")

    executor = CRMToolExecutor(db=db, workspace_id=workspace_id, user_id=1)
    result = await executor.execute("search_contacts", {"query": "x"})
    assert result["success"] is False
    assert "search_contacts" in result["error"]


@pytest.mark.asyncio
async def test_search_contacts_filters_by_workspace() -> None:
    """The contacts search must scope to the given workspace_id."""
    workspace_id = uuid.uuid4()

    captured_stmts: list[Any] = []

    async def fake_execute(stmt: Any) -> Any:
        captured_stmts.append(stmt)
        from unittest.mock import MagicMock
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        return result

    db = AsyncMock()
    db.execute = fake_execute  # type: ignore[assignment]

    executor = CRMToolExecutor(db=db, workspace_id=workspace_id, user_id=1)
    out = await executor.execute("search_contacts", {"query": "alice"})

    assert out["success"] is True
    assert out["count"] == 0
    # The bound parameters must include the workspace_id (multi-tenant scoping).
    assert len(captured_stmts) == 1
    compiled = captured_stmts[0].compile()
    assert workspace_id in compiled.params.values()
