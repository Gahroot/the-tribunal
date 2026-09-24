"""Weekly transcript replay samples calls, isolates errors and avoids PII logs."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.services.ai import prompt_scenario_suite as suite
from app.workers.prompt_replay_worker import PromptReplayWorker


@pytest.mark.asyncio
async def test_sample_filters_workspace_and_date_not_active_status():
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    workspace_id, agent_id = uuid4(), uuid4()
    db.execute.return_value.all.return_value = [
        (uuid4(), "private transcript", agent_id, workspace_id),
        (uuid4(), "second transcript", agent_id, workspace_id),
    ]
    with (
        patch.object(suite, "resolve_model", AsyncMock()) as resolve,
        patch.object(
            suite,
            "_verdict",
            AsyncMock(
                side_effect=[
                    RuntimeError("private provider payload"),
                    suite.SimulationVerdict("second", True, "good", 0.9),
                ]
            ),
        ),
    ):
        verdicts = await suite.replay_weekly_sample(db)
    assert len(verdicts) == 2
    assert not verdicts[0].success
    assert verdicts[1].success
    assert "private" not in repr(verdicts)
    resolve.assert_awaited_with(db, "transcript_judgment", workspace_id, agent_id)
    sql = str(
        db.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "conversations.workspace_id = agents.workspace_id" in sql
    assert "messages.created_at >=" in sql
    assert "LIMIT 50" in sql
    assert "is_active" not in sql
    assert "trim(messages.transcript)" in sql


@pytest.mark.asyncio
async def test_worker_logs_only_ids_and_numeric_verdicts():
    worker = PromptReplayWorker()
    worker.logger = MagicMock()
    session = AsyncMock()
    with (
        patch("app.workers.prompt_replay_worker.AsyncSessionLocal", return_value=session),
        patch(
            "app.workers.prompt_replay_worker.replay_weekly_sample",
            AsyncMock(
                return_value=[
                    suite.SimulationVerdict("replay-id", False, "private caller quote", 0.5)
                ]
            ),
        ),
    ):
        await worker._process_items()
    assert "private caller quote" not in str(worker.logger.mock_calls)
    worker.logger.info.assert_any_call("prompt_replay_summary", sampled=1, passed=0, mean_score=0.5)
    assert worker.POLL_INTERVAL_SECONDS == 7 * 86400
