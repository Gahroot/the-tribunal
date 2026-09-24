"""Tests for the transcript analysis worker."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.model_config import Selection
from app.workers import transcript_analysis_worker as worker_module


def _fake_session(messages: list[MagicMock]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = messages

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session.__ctx__ = ctx
    return session


@pytest.mark.asyncio
async def test_worker_analyzes_unanalyzed_messages() -> None:
    outcome = SimpleNamespace(signals={"duration_seconds": 42})
    msg = MagicMock()
    msg.id = "msg-1"
    msg.transcript = "Hello, I want to book an appointment."
    msg.call_outcome = outcome

    session = _fake_session([msg])

    analysis_payload = {
        "sentiment": "positive",
        "sentiment_score": 0.7,
        "intents": ["book"],
        "topics": ["scheduling"],
        "summary": "Wants appointment",
        "objections": [],
        "next_steps": ["confirm time"],
    }

    fake_sessionmaker = MagicMock(return_value=session.__ctx__)

    with (
        patch.object(worker_module, "AsyncSessionLocal", fake_sessionmaker),
        patch.object(
            worker_module,
            "analyze_transcript",
            AsyncMock(return_value=analysis_payload),
        ) as mocked_analyze,
        patch.object(worker_module, "judge_call", AsyncMock(return_value={"score": 0.8})),
        patch.object(worker_module, "record_bandit_reward", AsyncMock()),
        patch.object(
            worker_module,
            "resolve_model",
            AsyncMock(side_effect=lambda db, task, *ids: Selection(f"gpt-{task}")),
        ),
    ):
        worker = worker_module.TranscriptAnalysisWorker()
        await worker._process_items()

    mocked_analyze.assert_awaited_once_with(
        msg.transcript, selection=Selection("gpt-transcript_analysis")
    )
    assert outcome.signals["sentiment"] == "positive"
    assert outcome.signals["analyzed"] is True
    assert outcome.signals["judge"]["score"] == 0.8
    assert outcome.signals["duration_seconds"] == 42
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_marks_errors_without_infinite_retry() -> None:
    outcome = SimpleNamespace(signals={})
    msg = MagicMock()
    msg.id = "msg-err"
    msg.transcript = "garbled"
    msg.call_outcome = outcome

    session = _fake_session([msg])
    fake_sessionmaker = MagicMock(return_value=session.__ctx__)

    with (
        patch.object(worker_module, "AsyncSessionLocal", fake_sessionmaker),
        patch.object(
            worker_module,
            "analyze_transcript",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch.object(worker_module, "judge_call", AsyncMock(return_value={"score": 0.5})),
        patch.object(worker_module, "record_bandit_reward", AsyncMock()),
    ):
        worker = worker_module.TranscriptAnalysisWorker()
        await worker._process_items()

    assert outcome.signals["analyzed"] == "error"
    assert outcome.signals["judge"]["score"] == 0.5
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["no_transcript", "evaluation_failed"])
async def test_worker_judges_late_transcript_after_missing_evidence(error: str) -> None:
    outcome = SimpleNamespace(
        signals={
            "analyzed": "unavailable",
            "judge": {"human_review": True, "error": error},
            "judge_attempts": 3,
        }
    )
    msg = MagicMock()
    msg.id = "late-transcript"
    msg.transcript = "Agent: Hello. Prospect: Hi."
    msg.call_outcome = outcome
    session = _fake_session([msg])
    with (
        patch.object(worker_module, "AsyncSessionLocal", MagicMock(return_value=session.__ctx__)),
        patch.object(
            worker_module, "analyze_transcript", AsyncMock(return_value={"sentiment": "neutral"})
        ),
        patch.object(worker_module, "judge_call", AsyncMock(return_value={"score": 0.75})) as judge,
        patch.object(worker_module, "record_bandit_reward", AsyncMock()) as reward,
        patch.object(
            worker_module,
            "resolve_model",
            AsyncMock(side_effect=lambda db, task, *ids: Selection(f"gpt-{task}")),
        ),
    ):
        await worker_module.TranscriptAnalysisWorker()._process_items()
    judge.assert_awaited_once_with(msg.transcript, selection=Selection("gpt-transcript_judgment"))
    assert outcome.signals["judge"]["score"] == 0.75
    assert outcome.signals["analyzed"] is True
    reward.assert_awaited_once_with(session, outcome)


@pytest.mark.asyncio
async def test_worker_noop_on_empty_queue() -> None:
    session = _fake_session([])
    fake_sessionmaker = MagicMock(return_value=session.__ctx__)

    with (
        patch.object(worker_module, "AsyncSessionLocal", fake_sessionmaker),
        patch.object(worker_module, "analyze_transcript", AsyncMock()) as mocked_analyze,
    ):
        worker = worker_module.TranscriptAnalysisWorker()
        await worker._process_items()

    mocked_analyze.assert_not_awaited()
    session.commit.assert_not_awaited()
