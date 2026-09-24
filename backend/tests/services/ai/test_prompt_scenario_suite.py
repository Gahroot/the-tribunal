"""Regression tests for prompt promotion and transcript replay gates."""

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
async def test_judge_review_or_low_score_blocks() -> None:
    with (
        patch.object(
            suite,
            "judge_call",
            new_callable=AsyncMock,
            return_value={"score": 0.95, "human_review": True},
        ),
        patch.object(suite, "create_openai_client") as client,
    ):
        client.return_value.chat.completions.create = AsyncMock(
            return_value=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"success": true, "reason": "polite"}')
                    )
                ]
            )
        )
        verdict = await suite._verdict(
            "angry lead", "Caller: stop\nAgent: sorry", "Respect opt-out"
        )
        assert not verdict.success
        assert "human review" in verdict.reason


@pytest.mark.asyncio
async def test_system_approval_cannot_create_version_when_suite_fails() -> None:
    suggestion = SimpleNamespace(
        status="pending", suggested_prompt="unsafe", suggested_greeting=None
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
    version = SimpleNamespace(id="version-id")
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
