"""Call traces join across independent requests without exporting customer content."""

from decimal import Decimal
from time import time_ns
from unittest.mock import AsyncMock, MagicMock

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from app.services.ai import call_tracing


class _Exporter:
    def __init__(self):
        self.spans = []

    def export(self, spans):
        self.spans.extend(spans)

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


def test_call_hops_share_trace_and_first_audio_is_once(monkeypatch):
    exporter = _Exporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(call_tracing, "_TRACER", provider.get_tracer("test.calls"))

    with call_tracing.call_span("call-123", "telephony.telnyx.webhook"):
        pass
    with call_tracing.call_span("call-123", "voice.call") as root:
        with call_tracing.measure_first_audio():
            child = call_tracing.current_span("voice.tool", **{"tool.name": "book_appointment"})
            child.set_attribute("tool.success", True)
            child.set_attribute("appointment.booking_uid", "booking-123")
            child.end()
            call_tracing.record_first_audio()
            call_tracing.record_first_audio()
            call_tracing.record_tool_result(True)
            call_tracing.record_llm_cost("0.002", 20, 5)
        assert len(root.events) == 1
        assert root.attributes["voice.first_audio_ms"] >= 0
        assert root.attributes["voice.cost_complete"] is False
        assert "voice.estimated_cost_usd" not in root.attributes
        assert root.attributes["voice.tool_success_rate"] == 1.0
        assert root.attributes["voice.input_tokens"] == 20
    assert len(exporter.spans) == 3
    assert len({span.context.trace_id for span in exporter.spans}) == 1
    assert exporter.spans[1].attributes["appointment.booking_uid"] == "booking-123"
    assert all("phone" not in str(span.attributes) for span in exporter.spans)


def test_dial_and_webhook_join_same_trace_with_real_dial_latency(monkeypatch):
    exporter = _Exporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(call_tracing, "_TRACER", provider.get_tracer("test.calls"))
    start = time_ns() - 1_000_000
    with call_tracing.call_span("provider-123", "telephony.telnyx.dial", start_time=start):
        pass
    with call_tracing.call_span("provider-123", "telephony.telnyx.webhook"):
        pass
    assert exporter.spans[0].start_time == start
    assert exporter.spans[0].context.trace_id == exporter.spans[1].context.trace_id


def test_bad_call_id_does_not_export(monkeypatch):
    exporter = _Exporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(call_tracing, "_TRACER", provider.get_tracer("test.calls"))
    with call_tracing.call_span("x" * 257, "voice.call") as span:
        assert span is trace.INVALID_SPAN
    assert not exporter.spans


def test_provider_responses_are_measured_and_unknown_cost_is_not_zero(monkeypatch):
    exporter = _Exporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(call_tracing, "_TRACER", provider.get_tracer("test.calls"))
    monkeypatch.setenv("VOICE_TELNYX_USD_PER_MINUTE", "0.01")
    monkeypatch.setenv("VOICE_GROK_INPUT_USD_PER_MILLION", "2")
    monkeypatch.setenv("VOICE_GROK_OUTPUT_USD_PER_MILLION", "4")

    response = {
        "id": "r1",
        "status": "completed",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }
    with call_tracing.call_span("call-grok", "voice.call") as root:
        with call_tracing.measure_first_audio():
            call_tracing.mark_media_started()
            turns = call_tracing.ResponseSpans("xai", "grok-realtime")
            turns.start(response)
            turns.finish(response, call_tracing.grok_token_cost(response))
            turns.close()
        assert root.attributes["voice.cost_complete"] is True
        assert root.attributes["voice.estimated_cost_usd"] >= 0.0004
    assert exporter.spans[0].attributes["gen_ai.cost.usd"] == 0.0004

    monkeypatch.delenv("VOICE_GROK_OUTPUT_USD_PER_MILLION")
    assert call_tracing.grok_token_cost(response) is None
    assert call_tracing.estimated_cost("VOICE_TELNYX_USD_PER_MINUTE", Decimal(1)) == Decimal("0.01")


def test_live_turn_produces_span_without_fabricated_tokens(monkeypatch):
    from app.services.ai.live_voice_agent import LiveVoiceAgentSession

    exporter = _Exporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(call_tracing, "_TRACER", provider.get_tracer("test.calls"))
    monkeypatch.setenv("VOICE_TELNYX_USD_PER_MINUTE", "0")
    with call_tracing.call_span("call-live", "voice.call") as root:
        with call_tracing.measure_first_audio():
            session = LiveVoiceAgentSession(None)
            session._response_spans = call_tracing.ResponseSpans("openai-live", "gpt-live")
            session._handle_event({"type": "turn.created"})
            session._handle_event({"type": "turn.done"})
        assert root.attributes["voice.llm_calls"] == 1
        assert root.attributes["voice.cost_complete"] is False
    assert exporter.spans[0].name == "voice.llm"
    assert "gen_ai.usage.input_tokens" not in exporter.spans[0].attributes


def test_incomplete_llm_turn_prevents_false_cost_total(monkeypatch):
    exporter = _Exporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(call_tracing, "_TRACER", provider.get_tracer("test.calls"))
    monkeypatch.setenv("VOICE_TELNYX_USD_PER_MINUTE", "0")
    with call_tracing.call_span("call-dropped", "voice.call") as root:
        with call_tracing.measure_first_audio():
            turns = call_tracing.ResponseSpans("xai", "grok-realtime")
            turns.start({"id": "r1"})
            turns.close()
        assert root.attributes["voice.cost_complete"] is False
        assert "voice.estimated_cost_usd" not in root.attributes
    assert exporter.spans[0].attributes["gen_ai.response.status"] == "incomplete"


@pytest.mark.asyncio
async def test_booked_tool_is_linked_to_call_trace(monkeypatch):
    from app.services.ai.tool_executor import VoiceToolExecutor

    exporter = _Exporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(call_tracing, "_TRACER", provider.get_tracer("test.calls"))
    with call_tracing.call_span("call-booked", "voice.call") as root:
        with call_tracing.measure_first_audio():
            executor = VoiceToolExecutor(MagicMock(), call_control_id="call-booked")
            executor._execute = AsyncMock(
                return_value={"success": True, "booking_uid": "cal-booking"}
            )
            result = await executor.execute("book_appointment", {})
        assert root.attributes["voice.tool_calls"] == 1
        assert root.attributes["voice.tool_success_rate"] == 1.0
    assert result["booking_uid"] == "cal-booking"
    tool_span = next(span for span in exporter.spans if span.name == "voice.tool")
    assert tool_span.context.trace_id == exporter.spans[-1].context.trace_id
    assert tool_span.attributes["appointment.booking_uid"] == "cal-booking"


@pytest.mark.asyncio
async def test_failed_bridge_attempt_still_exports_call_span(monkeypatch):
    from app.websockets import voice_bridge

    exporter = _Exporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(call_tracing, "_TRACER", provider.get_tracer("test.calls"))
    request = AsyncMock(side_effect=RuntimeError("context lookup failed"))
    monkeypatch.setattr(voice_bridge, "_voice_stream_bridge_request", request)
    with pytest.raises(RuntimeError, match="context lookup failed"):
        await voice_bridge.voice_stream_bridge(None, "call-failed", False)
    assert exporter.spans[-1].name == "voice.call"
    assert exporter.spans[-1].attributes["call.id"] == "call-failed"
    assert exporter.spans[-1].status.status_code.name == "ERROR"
