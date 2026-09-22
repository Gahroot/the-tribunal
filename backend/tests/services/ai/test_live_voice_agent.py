"""Tests for the GPT-Live (Codex subscription) voice session.

The WebRTC peer is not exercised here; these cover the protocol v3 behaviours
that differ from the Realtime API path -- transcript turn bookkeeping,
delegation instead of function calls, mu-law passthrough, and usage metering.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from av import AudioFrame

from app.services.ai.live_audio import (
    BYTES_PER_FRAME,
    SAMPLE_RATE,
    MuLawRelayTrack,
    iter_mulaw_frames,
)
from app.services.ai.live_voice_agent import LiveVoiceAgentSession
from app.services.ai.protocols import receives_mulaw, sends_mulaw


class FakeChannel:
    """Stand-in for the ``oai-events`` data channel."""

    def __init__(self) -> None:
        self.readyState = "open"
        self.sent: list[dict] = []

    def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))


@pytest.fixture
def session() -> LiveVoiceAgentSession:
    """A session with a fake open data channel."""
    agent = LiveVoiceAgentSession(None)
    agent._channel = FakeChannel()
    agent._pc = object()  # is_connected only inspects the channel state
    return agent


def test_declares_mulaw_both_directions(session):
    """The bridge must skip conversion for this session."""
    assert sends_mulaw(session) is True
    assert receives_mulaw(session) is True


def test_user_transcript_accumulates_across_deltas(session):
    """Caller deltas build one turn instead of one entry per fragment."""
    session._handle_event({"type": "input_transcript.added", "text": "I need "})
    session._handle_event({"type": "input_transcript.added", "text": "an appointment"})

    # Not committed while deltas are still arriving.
    assert session.get_transcript_json() is None

    session._flush_user_turn()
    entries = json.loads(session.get_transcript_json())
    assert entries == [{"role": "user", "text": "I need an appointment"}]


def test_turn_done_does_not_close_partial_user_turn(session):
    """turn.done can carry partial text, so it must not commit the caller turn."""
    session._handle_event({"type": "input_transcript.added", "text": "hold on"})
    session._handle_event({"type": "turn.done"})

    assert session.get_transcript_json() is None
    assert session._user_turn_buffer == "hold on"


def test_turn_done_commits_agent_transcript(session):
    """The agent side is safe to close on turn.done."""
    session._handle_event({"type": "output_transcript.added", "text": "Sure, "})
    session._handle_event({"type": "output_transcript.added", "text": "one moment."})
    session._handle_event({"type": "turn.done"})

    entries = json.loads(session.get_transcript_json())
    assert entries == [{"role": "agent", "text": "Sure, one moment."}]


def test_input_audio_started_triggers_barge_in(session):
    """Caller speech sets the interruption event so buffered audio is dropped."""
    event = asyncio.Event()
    session.set_interruption_event(event)

    session._handle_event({"type": "input_audio.started"})

    assert event.is_set()
    assert session._is_interrupted is True


def test_usage_is_metered_locally(session):
    """Allowance is not exposed, so duration is tracked from session events."""
    session._handle_event(
        {
            "type": "session.usage.updated",
            "usage": {"audio_duration_ms": 42_000},
            "usage_limit": {"status": None, "reset_seconds": None},
        }
    )
    assert session._audio_duration_ms == 42_000


@pytest.mark.asyncio
async def test_delegation_runs_callback_and_returns_result(session):
    """A delegation executes the tool callback and appends the result."""
    calls: list[tuple[str, str, dict]] = []

    async def callback(call_id: str, name: str, args: dict) -> dict:
        calls.append((call_id, name, args))
        return {"status": "booked", "time": "Tuesday at 10"}

    session.set_tool_callback(callback)
    session._handle_event(
        {
            "type": "delegation.created",
            "item": {
                "id": "item_1",
                "type": "delegation",
                "content": [{"type": "input_text", "text": "book me for Tuesday"}],
                "target": "client",
            },
        }
    )
    await asyncio.gather(*list(session._tool_tasks))

    assert calls and calls[0][2] == {"request": "book me for Tuesday"}
    sent = session._channel.sent[-1]
    assert sent["type"] == "delegation.context.append"
    assert sent["delegation_item_id"] == "item_1"
    assert "booked" in sent["content"][0]["text"]


@pytest.mark.asyncio
async def test_delegation_without_callback_is_answered_not_dropped(session):
    """With no executor the model still gets a reply, so it does not stall."""
    session._handle_event(
        {
            "type": "delegation.created",
            "item": {"id": "item_2", "content": [{"type": "input_text", "text": "do it"}]},
        }
    )
    await asyncio.gather(*list(session._tool_tasks))

    sent = session._channel.sent[-1]
    assert sent["type"] == "delegation.context.append"
    assert sent["delegation_item_id"] == "item_2"


@pytest.mark.asyncio
async def test_delegation_failure_is_reported_back(session):
    """A failing tool does not kill the call; the model is told to move on."""

    async def failing(call_id: str, name: str, args: dict) -> dict:
        raise RuntimeError("calendar down")

    session.set_tool_callback(failing)
    session._handle_event(
        {
            "type": "delegation.created",
            "item": {"id": "item_3", "content": [{"type": "input_text", "text": "book"}]},
        }
    )
    await asyncio.gather(*list(session._tool_tasks))

    sent = session._channel.sent[-1]
    assert sent["type"] == "delegation.context.append"
    assert "failed" in sent["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_empty_delegation_is_skipped(session):
    """Filler delegations with no text must not become agent turns."""
    session.set_tool_callback(lambda *a: None)
    session._handle_event({"type": "delegation.created", "item": {"id": "item_4"}})

    assert not session._tool_tasks
    assert not session._channel.sent


@pytest.mark.asyncio
async def test_delegation_timeout_releases_the_call(session, monkeypatch):
    """A hanging tool must not leave the caller waiting in silence."""
    monkeypatch.setattr("app.services.ai.live_voice_agent.TOOL_TIMEOUT_SECONDS", 0.05)

    async def hanging(call_id: str, name: str, args: dict) -> dict:
        await asyncio.sleep(30)
        return {}

    session.set_tool_callback(hanging)
    session._handle_event(
        {
            "type": "delegation.created",
            "item": {"id": "item_5", "content": [{"type": "input_text", "text": "look it up"}]},
        }
    )
    await asyncio.wait_for(asyncio.gather(*list(session._tool_tasks)), timeout=5.0)

    sent = session._channel.sent[-1]
    assert sent["type"] == "delegation.context.append"
    assert sent["delegation_item_id"] == "item_5"
    assert "too long" in sent["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_delegations_do_not_overlap(session):
    """Concurrent agent turns would talk over each other, so they serialize."""
    active = 0
    max_active = 0

    async def tracking(call_id: str, name: str, args: dict) -> dict:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"ok": True}

    session.set_tool_callback(tracking)
    for index in range(3):
        session._handle_event(
            {
                "type": "delegation.created",
                "item": {
                    "id": f"item_p{index}",
                    "content": [{"type": "input_text", "text": "do a thing"}],
                },
            }
        )
    await asyncio.gather(*list(session._tool_tasks))

    assert max_active == 1
    assert len(session._channel.sent) == 3


@pytest.mark.asyncio
async def test_failed_connection_ends_the_audio_stream(session):
    """A dropped peer connection must not hang the bridge's receive loop."""

    class FailedPeer:
        # Name mirrors aiortc's RTCPeerConnection attribute.
        connectionState = "failed"  # noqa: N815

    session._pc = FailedPeer()
    session._on_connection_state_change()

    chunks = [chunk async for chunk in session.receive_audio_stream()]

    assert chunks == []
    assert not session._connected.is_set()


@pytest.mark.asyncio
async def test_audio_stream_ends_even_when_queue_is_full(session):
    """Teardown must not deadlock behind a saturated audio queue."""
    while not session._audio_queue.full():
        session._audio_queue.put_nowait(b"\xff" * 160)

    session._end_audio_stream()

    received = []
    async for chunk in session.receive_audio_stream():
        received.append(chunk)
    # The sentinel is reached rather than blocking forever.
    assert all(chunk == b"\xff" * 160 for chunk in received)


@pytest.mark.asyncio
async def test_cancel_response_drains_buffered_audio(session):
    """Barge-in must stop queued audio reaching the caller."""
    for _ in range(5):
        session._audio_queue.put_nowait(b"\xff" * 160)

    await session.cancel_response()

    assert session._audio_queue.empty()
    assert session._is_interrupted is True


def test_context_injection_uses_session_update(session):
    """v3 has no conversation.item.create, so context rides session.update."""
    asyncio.run(session.inject_context(contact_info={"name": "Dana"}))

    sent = session._channel.sent[-1]
    assert sent["type"] == "session.update"
    assert "Dana" in sent["session"]["prompt"]


def test_unknown_events_do_not_raise(session):
    """Unrecognised events are logged, never fatal."""
    session._handle_event({"type": "something.new", "payload": 1})
    session._handle_event({})


def test_invalid_json_on_channel_is_ignored(session):
    """Malformed channel data must not crash the call."""
    session._on_channel_message("not json")
    session._on_channel_message(b"\xff\xfe")


# ---------------------------------------------------------------------------
# Audio plumbing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relay_track_emits_fixed_size_frames():
    """Pushed mu-law is paced into 20 ms frames."""
    track = MuLawRelayTrack()
    track.push(b"\x7f" * (BYTES_PER_FRAME * 2))

    frame = await track.recv()

    assert frame.samples == BYTES_PER_FRAME
    assert frame.sample_rate == SAMPLE_RATE
    track.stop()


@pytest.mark.asyncio
async def test_relay_track_sends_silence_on_underrun():
    """An empty buffer yields silence rather than stalling the RTP stream."""
    track = MuLawRelayTrack()

    frame = await track.recv()

    assert frame.samples == BYTES_PER_FRAME
    track.stop()


@pytest.mark.asyncio
async def test_relay_track_paces_one_frame_per_period(monkeypatch):
    """Frame N must be due exactly N periods after the first, not N+1.

    Scheduling each frame a period late would add a constant 20 ms to every
    call. Time is frozen and sleeps are recorded, so this asserts the schedule
    itself rather than wall-clock timing.
    """
    delays: list[float] = []

    async def record(delay: float) -> None:
        delays.append(round(delay, 6))

    monkeypatch.setattr("app.services.ai.live_audio.time.monotonic", lambda: 1000.0)
    monkeypatch.setattr("app.services.ai.live_audio.asyncio.sleep", record)

    track = MuLawRelayTrack()
    track.push(b"\x7f" * (BYTES_PER_FRAME * 4))
    for _ in range(3):
        await track.recv()
    track.stop()

    # Frame 0 is immediate; frames 1 and 2 are due at 20 ms and 40 ms.
    assert delays == [0.02, 0.04]


def test_relay_track_drops_oldest_audio_when_flooded():
    """Unbounded buffering would add latency; the buffer is capped."""
    track = MuLawRelayTrack()
    track.push(b"\x00" * (BYTES_PER_FRAME * 500))

    assert len(track._buffer) <= BYTES_PER_FRAME * 100
    track.stop()


def test_iter_mulaw_frames_handles_planar_frames():
    """Planar plane 0 is already mono and must not be de-interleaved.

    Treating it as packed stereo would halve the sample count and play the
    caller's audio at double speed.
    """
    frame = AudioFrame(format="s16p", layout="stereo", samples=SAMPLE_RATE // 50)
    frame.sample_rate = SAMPLE_RATE
    for plane in frame.planes:
        plane.update(b"\x00\x01" * (SAMPLE_RATE // 50))

    chunks = list(iter_mulaw_frames(frame))

    assert len(b"".join(chunks)) == SAMPLE_RATE // 50


def test_iter_mulaw_frames_resamples_non_pcmu_audio():
    """If PCMU is not negotiated, decoded PCM is converted back to mu-law."""
    from av import AudioFrame

    frame = AudioFrame(format="s16", layout="mono", samples=960)
    frame.planes[0].update(b"\x00" * 1920)
    frame.sample_rate = 48000

    chunks = list(iter_mulaw_frames(frame))

    assert chunks
    # 48kHz -> 8kHz is a 6:1 reduction: 960 samples becomes 160 mu-law bytes.
    assert len(chunks[0]) == BYTES_PER_FRAME
