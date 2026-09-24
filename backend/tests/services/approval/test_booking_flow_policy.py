"""Live calendar/menu helpers must not bypass their parent action's policy."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.approval.approval_gate_service import ApprovalGateService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "parent"),
    [
        ("hold_booking_slot", "book_appointment"),
        ("booking_recovery", "book_appointment"),
        ("navigate_booking_menu", "send_dtmf"),
    ],
)
@pytest.mark.parametrize(
    ("policy", "decision"),
    [
        ("auto", "auto"),
        ("never", "blocked"),
        ("ask", "blocked"),
    ],
)
async def test_parent_policy_and_no_delayed_replay(tool, parent, policy, decision):
    profile = SimpleNamespace(action_policies={parent: policy}, default_policy="auto")
    db = SimpleNamespace(
        get=AsyncMock(return_value=None),
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=Mock(return_value=profile))
        ),
    )
    gate = ApprovalGateService()
    gate._create_pending_action = AsyncMock()
    result, _metadata = await gate.check_and_execute_or_queue(
        db=db,
        agent_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        action_type=tool,
        action_payload={},
        description="live booking helper",
    )
    assert result == decision
    gate._create_pending_action.assert_not_awaited()
