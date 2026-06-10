"""Tests for the live-sentiment escalation handler + agent-base wiring."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai import live_sentiment_escalation as esc
from app.services.ai.live_sentiment import LiveSentimentScorer, SentimentUpdate
from app.services.ai.voice_agent_base import VoiceAgentBase


def _update(*, escalate: bool, score: float = -0.8) -> SentimentUpdate:
    return SentimentUpdate(
        utterance_score=score,
        score=score,
        sentiment="negative",
        consecutive_negative=3,
        escalate=escalate,
        turns=3,
    )


@pytest.mark.asyncio
async def test_handler_persists_only_when_not_escalating() -> None:
    workspace_id = uuid.uuid4()
    message_id = uuid.uuid4()

    with (
        patch.object(esc, "_resolve_message_id", AsyncMock(return_value=message_id)),
        patch.object(esc, "_persist_live_signals", AsyncMock()) as persist,
        patch.object(esc, "_notify_operators", AsyncMock()) as notify,
        patch.object(esc, "_maybe_auto_transfer", AsyncMock(return_value=False)) as transfer,
    ):
        handler = esc.build_live_sentiment_handler(
            call_id="call-123",
            workspace_id=workspace_id,
            agent=None,
            contact_info=None,
            log=esc.logger,
        )
        await handler(_update(escalate=False))

    persist.assert_awaited_once()
    notify.assert_not_awaited()
    transfer.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_escalation_notifies_and_transfers() -> None:
    workspace_id = uuid.uuid4()
    message_id = uuid.uuid4()

    with (
        patch.object(esc, "_resolve_message_id", AsyncMock(return_value=message_id)),
        patch.object(esc, "_persist_live_signals", AsyncMock()) as persist,
        patch.object(esc, "_notify_operators", AsyncMock()) as notify,
        patch.object(esc, "_maybe_auto_transfer", AsyncMock(return_value=True)) as transfer,
    ):
        handler = esc.build_live_sentiment_handler(
            call_id="call-123",
            workspace_id=workspace_id,
            agent=None,
            contact_info={"name": "Jane"},
            log=esc.logger,
        )
        await handler(_update(escalate=True))

    persist.assert_awaited_once()
    notify.assert_awaited_once()
    transfer.assert_awaited_once()


@pytest.mark.asyncio
async def test_handler_resolves_message_id_once() -> None:
    workspace_id = uuid.uuid4()
    message_id = uuid.uuid4()

    resolve = AsyncMock(return_value=message_id)
    with (
        patch.object(esc, "_resolve_message_id", resolve),
        patch.object(esc, "_persist_live_signals", AsyncMock()),
    ):
        handler = esc.build_live_sentiment_handler(
            call_id="call-123",
            workspace_id=workspace_id,
            agent=None,
            contact_info=None,
            log=esc.logger,
        )
        await handler(_update(escalate=False))
        await handler(_update(escalate=False))

    resolve.assert_awaited_once()


# --- Agent-base wiring -------------------------------------------------------


class _FakeAgent(VoiceAgentBase):
    """Minimal concrete VoiceAgentBase to exercise the sentiment hook."""

    SERVICE_NAME = "fake_voice_agent"

    async def connect(self) -> bool:  # pragma: no cover - not exercised
        return True

    async def disconnect(self) -> None:  # pragma: no cover
        return None

    async def configure_session(self, **kwargs: Any) -> None:  # pragma: no cover
        return None

    async def send_audio_chunk(self, audio_data: bytes) -> None:  # pragma: no cover
        return None

    def receive_audio_stream(self) -> AsyncIterator[bytes]:  # pragma: no cover
        async def _gen() -> AsyncIterator[bytes]:
            if False:
                yield b""

        return _gen()

    async def trigger_initial_response(self, **kwargs: Any) -> None:  # pragma: no cover
        return None

    async def inject_context(self, **kwargs: Any) -> None:  # pragma: no cover
        return None

    async def cancel_response(self) -> None:  # pragma: no cover
        return None


@pytest.mark.asyncio
async def test_agent_base_fires_escalation_callback_on_sustained_negative() -> None:
    agent = _FakeAgent()
    scorer = LiveSentimentScorer(negative_threshold=-0.4, sustained_turns=3, smoothing=0.5)

    updates: list[SentimentUpdate] = []

    async def on_update(update: SentimentUpdate) -> None:
        updates.append(update)

    agent.enable_live_sentiment(scorer, on_update)

    # Three sustained negative caller turns should escalate exactly once.
    agent._add_user_transcript("this is terrible and awful")
    agent._add_user_transcript("absolutely the worst, I hate it")
    agent._add_user_transcript("this is ridiculous and unacceptable")

    # Snapshot the scheduled callback tasks before awaiting (the done-callback
    # removes them from the set as they finish), then drain them.
    pending = list(agent._sentiment_tasks)
    await asyncio.gather(*pending)

    assert len(updates) == 3
    assert [u.escalate for u in updates] == [False, False, True]
    assert agent.last_sentiment is not None
    assert agent.last_sentiment.sentiment == "negative"
