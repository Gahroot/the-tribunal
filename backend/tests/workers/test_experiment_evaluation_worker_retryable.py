"""ExperimentEvaluationWorker — RetryableWorker contract."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.workers.base import BaseWorker
from app.workers.experiment_evaluation_worker import ExperimentEvaluationWorker
from app.workers.retryable import RetryableWorker
from tests.workers._retryable_helpers import wire_worker_for_retry_test


@pytest.mark.asyncio
@pytest.mark.parametrize("passes", [True, False])
async def test_winner_must_pass_scenarios_before_activation(passes):
    version = SimpleNamespace(id=uuid4(), agent_id=uuid4(), version_number=2)
    comparison = SimpleNamespace(winner_id=version.id, winner_probability=0.99)
    db = AsyncMock()
    db.scalar.return_value = uuid4()
    service = SimpleNamespace(activate_version=AsyncMock())
    with (
        patch("app.workers.experiment_evaluation_worker.resolve_model", AsyncMock()),
        patch(
            "app.workers.experiment_evaluation_worker.require_scenario_pass",
            AsyncMock(side_effect=None if passes else ValueError("scenario failed")),
        ) as gate,
    ):
        if passes:
            await ExperimentEvaluationWorker()._declare_winner(
                db, MagicMock(), service, comparison, [version]
            )
            service.activate_version.assert_awaited_once_with(db, version.id)
        else:
            with pytest.raises(ValueError, match="scenario failed"):
                await ExperimentEvaluationWorker()._declare_winner(
                    db, MagicMock(), service, comparison, [version]
                )
            service.activate_version.assert_not_awaited()
        gate.assert_awaited_once()
        assert gate.await_args.args[0] is version


def test_class_inherits_retryable_and_base() -> None:
    assert issubclass(ExperimentEvaluationWorker, RetryableWorker)
    assert issubclass(ExperimentEvaluationWorker, BaseWorker)


def test_retry_configuration() -> None:
    assert ExperimentEvaluationWorker.COMPONENT_NAME == "experiment_evaluation"
    assert ExperimentEvaluationWorker.max_retries == 3
    assert ExperimentEvaluationWorker.backoff_base_seconds == 2.0


@pytest.mark.asyncio
async def test_failed_agent_evaluation_routes_to_dlq() -> None:
    worker = ExperimentEvaluationWorker()
    recorder = wire_worker_for_retry_test(worker)

    agent = MagicMock(id=uuid4(), name="agent-x")
    db = MagicMock()

    async def fail(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("eval failed")

    item_key = f"agent:{agent.id}"
    await worker.execute_with_retry(fail, db, agent, item_key=item_key)

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["worker_name"] == "experiment_evaluation"
    assert recorder.calls[0]["item_key"] == item_key
