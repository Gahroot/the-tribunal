"""Reward waits for a completed voice judgment and is written once."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.ai.bandit_reward_service import BanditRewardService


@pytest.mark.asyncio
async def test_voice_reward_deferred_until_judged_then_idempotent():
    decision = SimpleNamespace(
        agent_id="agent",
        arm_id="version",
        observed_reward=None,
        reward_observed_at=None,
        id="decision",
    )
    version = SimpleNamespace(
        id="version", bandit_alpha=1.0, bandit_beta=1.0, total_reward=0.0, reward_count=0
    )
    message = SimpleNamespace(channel="voice", duration_seconds=120)
    agent = SimpleNamespace(bandit_reward_config={})
    outcome = SimpleNamespace(
        id="outcome", message_id="message", outcome_type="completed", signals={}
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: decision),
                SimpleNamespace(scalar_one_or_none=lambda: decision),
                SimpleNamespace(scalar_one_or_none=lambda: decision),
                SimpleNamespace(scalar_one_or_none=lambda: decision),
                SimpleNamespace(scalar_one_or_none=lambda: version),
                SimpleNamespace(scalar_one_or_none=lambda: decision),
            ]
        ),
        get=AsyncMock(side_effect=[message, message, message, message, agent]),
        commit=AsyncMock(),
    )
    service = BanditRewardService()
    assert await service.record_reward(db, outcome) is None
    db.commit.assert_not_awaited()
    outcome.signals = {"judge": {"human_review": True, "error": "no_transcript"}}
    assert await service.record_reward(db, outcome) is None
    outcome.signals = {
        "judge": {"human_review": True, "error": "evaluation_failed"},
        "judge_attempts": 3,
    }
    assert await service.record_reward(db, outcome) is None
    db.commit.assert_not_awaited()
    outcome.signals = {
        "judge": {
            "score": 0.8,
            "human_review": False,
            "scores": {
                name: {"score": 3, "quote": "Agent: Hi"}
                for name in ("opening", "listening", "objection_handling", "compliance", "close")
            },
        }
    }
    reward = await service.record_reward(db, outcome)
    assert reward == pytest.approx(0.6 * 0.3 + 0.3 * 0.8 + 0.1)
    assert await service.record_reward(db, outcome) == reward
    assert version.reward_count == 1
    db.commit.assert_awaited_once()
