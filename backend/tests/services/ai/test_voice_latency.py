"""Deterministic budget checks exercise real tracing and Telnyx frame delivery."""

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.services.ai import call_tracing, voice_latency
from app.services.ai.elevenlabs_voice_agent import ElevenLabsVoiceAgentSession
from app.services.ai.grok import GrokVoiceAgentSession
from app.services.ai.live_voice_agent import LiveVoiceAgentSession
from app.services.ai.voice_agent import VoiceAgentSession
from app.websockets.voice_bridge import _receive_from_provider_and_send_to_telnyx


@pytest.fixture
def harness(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("budget.test")
    monkeypatch.setattr(call_tracing, "_TRACER", tracer)
    monkeypatch.setattr(voice_latency, "_TRACER", tracer)
    clock = [10.0]
    # Replace this module's clock, not asyncio's global monotonic clock.
    monkeypatch.setattr(voice_latency, "time", MagicMock(monotonic=lambda: clock[0]))
    return exporter, clock


@pytest.mark.parametrize(
    "elapsed,target_met,alerts",
    [(499, True, 0), (500, False, 0), (1000, False, 0), (1001, False, 1), (2100, False, 1)],
)
def test_thresholds_exact_and_metrics_without_sampling(harness, elapsed, target_met, alerts):
    exporter, clock = harness
    metric = voice_latency.voice_audio_latency_regressions_total.labels("grok", "turn")
    before = metric._value.get()
    with call_tracing.call_span("budget-call", "voice.call") as root:
        budget = voice_latency.VoiceLatencyBudget(root, "grok")
        budget.start("turn")
        budget.start("turn")  # Duplicate events cannot reset the clock.
        clock[0] += elapsed / 1000
        budget.audio_sent()
        budget.audio_sent()
        budget.close()
    spans = [s for s in exporter.get_finished_spans() if s.name == "voice.audio_latency"]
    assert len(spans) == 1
    assert spans[0].attributes["voice.latency.ms"] == pytest.approx(elapsed)
    assert spans[0].attributes["voice.latency.target_met"] is target_met
    assert metric._value.get() - before == alerts


@pytest.mark.asyncio
async def test_missing_audio_alerts_once_and_teardown_cancels_timer(harness):
    _, clock = harness
    with call_tracing.call_span("no-audio", "voice.call") as root:
        budget = voice_latency.VoiceLatencyBudget(root, "openai")
        # Already over budget: real event-loop watchdog must fire without audio.
        budget.start("turn", clock[0] - 2)
        pending = budget.pending["turn"]
        await asyncio.sleep(0.01)
        assert pending.alerted
        assert len(pending.span.events) == 1
        budget.audio_sent()
        assert len(pending.span.events) == 1
        assert pending.timer.cancelled()
        budget.start("turn")
        pending = budget.pending["turn"]
        budget.close()
        assert pending.timer.cancelled()
        assert not budget.pending
        budget.start("turn")
        assert not budget.pending


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "grok", "elevenlabs", "live"])
async def test_each_turn_measured_at_telnyx_send_without_http(harness, monkeypatch, provider):
    exporter, clock = harness

    async def forbid_http(*args, **kwargs):
        pytest.fail("HTTP is forbidden in the audio hot path")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbid_http)
    with (
        call_tracing.call_span(f"call-{provider}", "voice.call"),
        call_tracing.measure_first_audio(started_at=clock[0]),
    ):
        call_tracing.configure_latency_budget(provider)
        factories = {
            "openai": lambda: VoiceAgentSession("test"),
            "grok": lambda: GrokVoiceAgentSession("test"),
            "elevenlabs": lambda: ElevenLabsVoiceAgentSession("test", "test"),
            "live": lambda: LiveVoiceAgentSession(None),
        }
        session = factories[provider]()
        session.OUTPUT_AUDIO_FORMAT = "ulaw"
        expected_phase = "response" if provider == "live" else "turn"

        async def frames():
            yield b"\xff" * 160  # Greeting
            for _ in range(2):
                session.observe_provider_event({"type": "input_audio_buffer.speech_started"})
                session.observe_provider_event(
                    {
                        "type": "turn.created"
                        if provider == "live"
                        else "input_audio_buffer.speech_stopped"
                    }
                )
                clock[0] += 0.25
                yield b"\xff" * 160

        session.receive_audio_stream = frames
        socket = MagicMock(send_text=AsyncMock())
        ready = asyncio.Event()
        ready.set()
        await _receive_from_provider_and_send_to_telnyx(socket, session, MagicMock(), ready, {})
        assert socket.send_text.await_count == 3
        for call in socket.send_text.call_args_list:
            assert len(base64.b64decode(json.loads(call.args[0])["media"]["payload"])) == 160
    measurements = [s for s in exporter.get_finished_spans() if s.name == "voice.audio_latency"]
    assert [s.attributes["voice.latency.phase"] for s in measurements] == [
        "greeting",
        expected_phase,
        expected_phase,
    ]
    assert all(s.attributes["voice.provider_path"] == provider for s in measurements)
    assert len({s.context.trace_id for s in measurements}) == 1


def test_metrics_work_without_recording_span(harness):
    _, clock = harness
    metric = voice_latency.voice_audio_latency_regressions_total.labels("openai", "turn")
    before = metric._value.get()
    budget = voice_latency.VoiceLatencyBudget(trace.INVALID_SPAN, "openai")
    budget.start("turn")
    clock[0] += 1.1
    budget.audio_sent()
    budget.close()
    assert metric._value.get() - before == 1


@pytest.mark.asyncio
async def test_failed_telnyx_send_is_not_successful_audio(harness):
    exporter, clock = harness
    with (
        call_tracing.call_span("failed-send", "voice.call"),
        call_tracing.measure_first_audio(started_at=clock[0]),
    ):
        call_tracing.configure_latency_budget("openai")
        session = VoiceAgentSession("test")
        session.OUTPUT_AUDIO_FORMAT = "ulaw"

        async def frames():
            yield b"\xff" * 160

        session.receive_audio_stream = frames
        ready = asyncio.Event()
        ready.set()
        socket = MagicMock(send_text=AsyncMock(side_effect=RuntimeError("disconnected")))
        await _receive_from_provider_and_send_to_telnyx(socket, session, MagicMock(), ready, {})
    spans = [s for s in exporter.get_finished_spans() if s.name == "voice.audio_latency"]
    assert len(spans) == 1
    assert spans[0].attributes["voice.latency.outcome"] == "no_audio"
    assert "voice.latency.ms" not in spans[0].attributes


def test_barge_in_and_call_isolation(harness):
    exporter, _ = harness
    with call_tracing.call_span("a", "voice.call") as root:
        a = voice_latency.VoiceLatencyBudget(root, "grok")
        a.start("turn")
        a.interrupt()
        a.audio_sent()
        a.close()
    with call_tracing.call_span("b", "voice.call") as root:
        b = voice_latency.VoiceLatencyBudget(root, "untrusted-provider")
        b.start("turn")
        b.audio_sent()
        b.close()
    spans = [s for s in exporter.get_finished_spans() if s.name == "voice.audio_latency"]
    assert spans[0].attributes["voice.latency.outcome"] == "interrupted"
    assert "voice.latency.ms" not in spans[0].attributes
    assert spans[1].attributes["voice.provider_path"] == "unknown"
    assert spans[0].context.trace_id != spans[1].context.trace_id
