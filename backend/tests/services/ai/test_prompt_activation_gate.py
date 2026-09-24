"""Automatic promotion requires both independent outcome and rubric evidence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai.model_config import Selection
from app.workers.prompt_improvement_worker import PromptImprovementWorker


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("score", "bookings", "shown", "review", "expected"),
    [
        (0.9, 0, 0, False, False),  # Transcript-only success is not a booking.
        (0.5, 3, 0, False, False),  # Booking alone is not sufficient quality.
        (0.9, 3, 0, True, False),  # Review-needed evidence cannot auto-promote.
        (0.9, 3, 0, False, True),
        (0.9, 0, 2, False, True),  # Attended appointments are real outcomes too.
    ],
)
async def test_promotion_gate(score, bookings, shown, review, expected):
    rows = [
        (
            {
                "judge": {
                    "score": score,
                    "human_review": review,
                    "rubric_version": 1,
                    "confidence": 0.9,
                    "scores": {
                        name: {"score": 3, "quote": "Hello"}
                        for name in (
                            "opening",
                            "listening",
                            "objection_handling",
                            "compliance",
                            "close",
                        )
                    },
                }
            },
            "success" if i < bookings else None,
            i < shown,
        )
        for i in range(10)
    ]
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))
    worker = PromptImprovementWorker()
    version = SimpleNamespace(id="test-version")
    assert await worker._can_auto_activate(db, version) is expected


@pytest.mark.asyncio
async def test_promotion_uses_candidate_evidence_not_source():
    candidate = SimpleNamespace(id="candidate", version_number=2)
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: [candidate])),
        commit=AsyncMock(),
    )
    worker = PromptImprovementWorker()
    agent = SimpleNamespace(id="agent", workspace_id="workspace")
    with patch.object(worker, "_can_auto_activate", AsyncMock(return_value=False)) as gate:
        assert await worker._promote_tested_candidate(db, agent) is False
    gate.assert_awaited_once_with(db, candidate)
    db.commit.assert_not_awaited()
    db.execute.assert_awaited_once()  # No promotion write, however good the source is.


@pytest.mark.asyncio
async def test_tested_candidate_can_be_promoted():
    candidate = SimpleNamespace(id="candidate", version_number=2)
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalars=lambda: [candidate]),
                SimpleNamespace(first=lambda: ("source",)),
            ]
        ),
        commit=AsyncMock(),
    )
    worker = PromptImprovementWorker()
    with (
        patch.object(worker, "_can_auto_activate", AsyncMock(return_value=True)),
        patch(
            "app.workers.prompt_improvement_worker.resolve_model",
            new_callable=AsyncMock,
            return_value=Selection("gpt-test"),
        ) as resolve,
        patch(
            "app.workers.prompt_improvement_worker.require_scenario_pass",
            new_callable=AsyncMock,
        ) as scenarios,
    ):
        agent = SimpleNamespace(id="agent", workspace_id="workspace")
        assert await worker._promote_tested_candidate(db, agent) is True
    scenarios.assert_awaited_once_with(
        candidate, simulation=Selection("gpt-test"), judgment=Selection("gpt-test")
    )
    assert resolve.await_count == 2
    assert db.execute.await_count == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_candidate_failing_scenarios_cannot_replace_live_version():
    candidate = SimpleNamespace(id="candidate", version_number=2)
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: [candidate])),
        commit=AsyncMock(),
    )
    worker = PromptImprovementWorker()
    with (
        patch.object(worker, "_can_auto_activate", AsyncMock(return_value=True)),
        patch(
            "app.workers.prompt_improvement_worker.resolve_model",
            new_callable=AsyncMock,
            return_value=Selection("gpt-test"),
        ),
        patch(
            "app.workers.prompt_improvement_worker.require_scenario_pass",
            new_callable=AsyncMock,
            side_effect=ValueError("scenario failed"),
        ),
        pytest.raises(ValueError, match="scenario failed"),
    ):
        agent = SimpleNamespace(id="agent", workspace_id="workspace")
        await worker._promote_tested_candidate(db, agent)
    db.execute.assert_awaited_once()
    db.commit.assert_not_awaited()
