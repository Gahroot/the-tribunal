"""Regression tests for prompt promotion and transcript replay gates."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai import prompt_scenario_suite as suite
from app.services.ai.prompt_improvement_service import PromptImprovementService


@pytest.mark.asyncio
async def test_all_scripted_personas_run_and_fail_closed() -> None:
    version = SimpleNamespace(system_prompt="Be polite", initial_greeting=None)
    with (
        patch.object(
            suite, "_simulate", new_callable=AsyncMock, return_value="Agent: hello"
        ) as simulate,
        patch.object(
            suite,
            "_verdict",
            new_callable=AsyncMock,
            side_effect=lambda name, *_: suite.SimulationVerdict(
                name, name != "wrong number", "wrong number not respected", 0.9
            ),
        ),
    ):
        verdicts = await suite.run_scenarios(version)
        assert [v.name for v in verdicts] == [s.name for s in suite.SCENARIOS]
        assert simulate.await_count == 8
        assert not all(v.success for v in verdicts)
        with pytest.raises(ValueError, match="wrong number"):
            await suite.require_scenario_pass(version)


@pytest.mark.asyncio
async def test_provider_error_returns_failure_and_runs_remaining_personas() -> None:
    with (
        patch.object(
            suite, "_simulate", new_callable=AsyncMock, side_effect=RuntimeError("private")
        ),
        patch.object(suite, "_verdict", new_callable=AsyncMock) as judge,
    ):
        verdicts = await suite.run_scenarios(
            SimpleNamespace(system_prompt="Be polite", initial_greeting=None)
        )
    assert len(verdicts) == 8
    assert all(not v.success and v.score == 0 for v in verdicts)
    assert all("private" not in v.reason for v in verdicts)
    judge.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed() -> None:
    with (
        patch.object(
            suite, "_simulate", new_callable=AsyncMock, side_effect=asyncio.CancelledError
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await suite.run_scenarios(SimpleNamespace(system_prompt="Be polite", initial_greeting=None))


@pytest.mark.asyncio
async def test_silent_caller_waits_for_second_silence_before_judgment() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Are you there?"))]
    )
    with patch.object(suite, "create_openai_client") as client:
        client.return_value.chat.completions.create = AsyncMock(return_value=response)
        transcript = await suite._simulate(
            SimpleNamespace(system_prompt="Be polite", initial_greeting=None),
            next(s for s in suite.SCENARIOS if s.name == "silent breather"),
        )
        assert client.return_value.chat.completions.create.await_count == 2
    assert transcript.count("Caller:") == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("score", "review", "decision", "passed"),
    [
        (0.95, True, True, False),
        (0.79, False, True, False),
        (0.8, False, True, True),
        (0.95, False, False, False),
    ],
)
async def test_judge_review_or_low_score_blocks(score, review, decision, passed) -> None:
    with (
        patch.object(
            suite,
            "judge_call",
            new_callable=AsyncMock,
            return_value={"score": score, "human_review": review},
        ),
        patch.object(suite, "create_openai_client"),
        patch.object(
            suite,
            "generate_structured",
            new_callable=AsyncMock,
            return_value=suite.ScenarioDecision(success=decision, reason="scenario decision"),
        ),
    ):
        verdict = await suite._verdict(
            "angry lead", "Caller: stop\nAgent: sorry", "Respect opt-out"
        )
        assert verdict.success is passed
        if review:
            assert "human review" in verdict.reason
        elif score < suite.MIN_SCORE:
            assert "below" in verdict.reason


@pytest.mark.asyncio
async def test_system_approval_cannot_create_version_when_suite_fails() -> None:
    suggestion = SimpleNamespace(
        status="pending",
        suggested_prompt="unsafe",
        suggested_greeting=None,
        agent_id=uuid.uuid4(),
    )
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = suggestion
    service = PromptImprovementService()
    service._prompt_service.create_version = AsyncMock()
    with (
        patch(
            "app.services.ai.prompt_scenario_suite.require_scenario_pass",
            new_callable=AsyncMock,
            side_effect=ValueError("scenario failed"),
        ),
        pytest.raises(ValueError, match="scenario failed"),
    ):
        await service.approve_suggestion(db, uuid.uuid4(), user_id=None)
    service._prompt_service.create_version.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_is_limited_to_fifty_and_does_not_return_transcripts() -> None:
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.all.return_value = [("Caller: hello\nAgent: hi",)]
    version = SimpleNamespace(id="version-id", agent_id=uuid.uuid4())
    with patch.object(
        suite,
        "_verdict",
        new_callable=AsyncMock,
        return_value=suite.SimulationVerdict("replay-1", True, "passed", 0.9),
    ):
        verdicts = await suite.replay_recent_calls(db, version)
    assert len(verdicts) == 1
    assert "Caller:" not in repr(verdicts)
    with pytest.raises(ValueError):
        await suite.replay_recent_calls(db, version, sample_size=51)
