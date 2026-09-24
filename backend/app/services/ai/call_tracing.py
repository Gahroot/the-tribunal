"""Per-call OTLP spans. Only opaque provider IDs and aggregate usage leave the process.

A stable trace ID joins independent Telnyx webhooks and the media WebSocket without
relying on Telnyx to propagate traceparent. Export is batched by core.telemetry.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import (
    NonRecordingSpan,
    Span,
    SpanContext,
    TraceFlags,
    set_span_in_context,
)

_TRACER = trace.get_tracer("app.services.ai.call_tracing")
_CALL_STARTED: ContextVar[float | None] = ContextVar("call_started", default=None)
_FIRST_AUDIO: ContextVar[bool] = ContextVar("first_audio", default=False)
_MEDIA_STARTED: ContextVar[float | None] = ContextVar("media_started", default=None)


@dataclass
class _Totals:
    cost_usd: Decimal = Decimal(0)
    cost_complete: bool = True
    llm_calls: int = 0
    provider_costs: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    tool_successes: int = 0


_TOTALS: ContextVar[_Totals | None] = ContextVar("call_totals", default=None)


def record_llm_cost(
    cost: str | None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    *,
    totals: _Totals | None = None,
) -> None:
    totals = totals if totals is not None else _TOTALS.get()
    if totals is not None:
        totals.llm_calls += 1
        if type(input_tokens) is int and input_tokens >= 0:
            totals.input_tokens += input_tokens
        if type(output_tokens) is int and output_tokens >= 0:
            totals.output_tokens += output_tokens
        if cost is None:
            totals.cost_complete = False
        else:
            totals.cost_usd += Decimal(cost)


def record_provider_cost(cost: Decimal | None) -> None:
    """Add a provider charge; unknown prices make the call total unavailable."""
    totals = _TOTALS.get()
    if totals is not None:
        totals.provider_costs += 1
        if cost is None:
            totals.cost_complete = False
        else:
            totals.cost_usd += cost


def configured_rate(name: str) -> Decimal | None:
    """Operator-supplied estimate, not an invented or assumed provider tariff."""
    if name not in {
        "VOICE_TELNYX_USD_PER_MINUTE",
        "VOICE_GROK_INPUT_USD_PER_MILLION",
        "VOICE_GROK_OUTPUT_USD_PER_MILLION",
        "VOICE_ELEVENLABS_USD_PER_1000_CHARS",
    }:
        return None
    raw = os.getenv(name)
    try:
        rate = Decimal(raw) if raw is not None else None
        return rate if rate is not None and rate.is_finite() and 0 <= rate <= 100 else None
    except (ValueError, ArithmeticError):
        return None


def estimated_cost(rate_name: str, units: Decimal) -> Decimal | None:
    rate = configured_rate(rate_name)
    return rate * units if rate is not None else None


def grok_token_cost(response: object) -> str | None:
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return None
    input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    input_rate = configured_rate("VOICE_GROK_INPUT_USD_PER_MILLION")
    output_rate = configured_rate("VOICE_GROK_OUTPUT_USD_PER_MILLION")
    if (
        type(input_tokens) is not int
        or type(output_tokens) is not int
        or not 0 <= input_tokens <= 1_000_000_000
        or not 0 <= output_tokens <= 1_000_000_000
        or input_rate is None
        or output_rate is None
    ):
        return None
    return str((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000)


def call_totals() -> _Totals | None:
    """Capture per-call counters before passing callbacks to an external provider."""
    return _TOTALS.get()


def mark_media_started() -> None:
    _MEDIA_STARTED.set(time.monotonic())


def record_tool_result(success: bool, *, totals: _Totals | None = None) -> None:
    totals = totals if totals is not None else _TOTALS.get()
    if totals is not None:
        totals.tool_calls += 1
        totals.tool_successes += int(success)


def _parent(call_id: str) -> Context:
    # Fixed synthetic parent; all processes derive the same trace ID for this call.
    # Never use phone numbers, transcripts, tool arguments, or provider secrets.
    trace_id = int.from_bytes(hashlib.sha256(call_id.encode()).digest()[:16], "big") or 1
    return set_span_in_context(
        NonRecordingSpan(
            SpanContext(
                trace_id=trace_id,
                span_id=1,
                is_remote=True,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            )
        )
    )


@contextmanager
def call_span(
    call_id: str,
    name: str,
    *,
    attributes: Mapping[str, str] | None = None,
    start_time: int | None = None,
) -> Iterator[Span]:
    """Start a call-scoped span (also usable by independent webhook requests)."""
    if not call_id or len(call_id) > 256:
        yield trace.INVALID_SPAN
        return
    with _TRACER.start_as_current_span(
        name,
        context=_parent(call_id),
        attributes={"call.id": call_id, **(attributes or {})},
        start_time=start_time,
    ) as span:
        yield span


def current_span(name: str, **attributes: str) -> Span:
    """Start a child span; caller must end it, including on error paths."""
    return _TRACER.start_span(name, attributes=attributes)


class ResponseSpans:
    """Bounded response lifecycle tracker shared by realtime voice providers."""

    def __init__(self, provider: str, model: str = "") -> None:
        self.provider = provider
        self.model = model
        self._context: Context = set_span_in_context(trace.get_current_span())
        self._totals = _TOTALS.get()
        self._spans: dict[str, Span] = {}

    def start(self, response: object) -> None:
        data = response if isinstance(response, dict) else {}
        response_id = data.get("id")
        if not isinstance(response_id, str) or not response_id or len(self._spans) >= 16:
            return
        if response_id in self._spans:
            return
        self._spans[response_id] = _TRACER.start_span(
            "voice.llm",
            context=self._context,
            attributes={"gen_ai.system": self.provider, "gen_ai.request.model": self.model},
        )

    def finish(self, response: object, cost: str | None = None) -> None:
        data = response if isinstance(response, dict) else {}
        response_id = data.get("id")
        span = self._spans.pop(response_id, None) if isinstance(response_id, str) else None
        if span is None:
            # A provider may omit response.created after reconnect. Export the
            # completed call without inventing its latency.
            span = _TRACER.start_span(
                "voice.llm",
                context=self._context,
                attributes={
                    "gen_ai.system": self.provider,
                    "gen_ai.request.model": self.model,
                    "voice.llm.start_missing": True,
                },
            )
        usage = data.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        for name, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens)):
            if type(value) is int and 0 <= value <= 1_000_000_000:
                span.set_attribute(f"gen_ai.usage.{name}", value)
        if cost is not None:
            span.set_attribute("gen_ai.cost.usd", float(cost))
        span.set_attribute("gen_ai.response.status", str(data.get("status", ""))[:32])
        record_llm_cost(cost, input_tokens, output_tokens, totals=self._totals)
        span.end()

    def close(self) -> None:
        for span in self._spans.values():
            span.set_attribute("gen_ai.response.status", "incomplete")
            record_llm_cost(None, totals=self._totals)
            span.end()
        self._spans.clear()


@contextmanager
def measure_first_audio(started_at: float | None = None) -> Iterator[None]:
    started_value = started_at if started_at is not None else time.monotonic()
    started = _CALL_STARTED.set(started_value)
    first = _FIRST_AUDIO.set(False)
    totals = _Totals()
    total_token = _TOTALS.set(totals)
    media_token = _MEDIA_STARTED.set(None)
    try:
        yield
    finally:
        span = trace.get_current_span()
        media_started = _MEDIA_STARTED.get()
        elapsed_seconds = max(0, time.monotonic() - media_started) if media_started else 0
        telephony_cost = (
            estimated_cost("VOICE_TELNYX_USD_PER_MINUTE", Decimal(str(elapsed_seconds)) / 60)
            if media_started is not None
            else None
        )
        record_provider_cost(telephony_cost)
        if span.is_recording():
            span.set_attribute("telephony.duration_seconds", round(elapsed_seconds, 3))
            if telephony_cost is not None:
                span.set_attribute("telephony.estimated_cost_usd", float(telephony_cost))
            span.set_attribute("voice.llm_calls", totals.llm_calls)
            span.set_attribute("voice.input_tokens", totals.input_tokens)
            span.set_attribute("voice.output_tokens", totals.output_tokens)
            span.set_attribute("voice.tool_calls", totals.tool_calls)
            span.set_attribute("voice.tool_successes", totals.tool_successes)
            if totals.tool_calls:
                span.set_attribute(
                    "voice.tool_success_rate", totals.tool_successes / totals.tool_calls
                )
                span.set_attribute(
                    "voice.tool_success_target_met",
                    totals.tool_successes / totals.tool_calls > 0.95,
                )
            span.set_attribute("voice.cost_complete", totals.cost_complete)
            if totals.cost_complete:
                span.set_attribute("voice.estimated_cost_usd", float(totals.cost_usd))
        _MEDIA_STARTED.reset(media_token)
        _TOTALS.reset(total_token)
        _FIRST_AUDIO.reset(first)
        _CALL_STARTED.reset(started)


def record_first_audio() -> None:
    """Record first outbound media frame; independent of the provider's first chunk."""
    started_at = _CALL_STARTED.get()
    if started_at is None or _FIRST_AUDIO.get():
        return
    _FIRST_AUDIO.set(True)
    span = trace.get_current_span()
    if span.is_recording():
        ms = max(0, round((time.monotonic() - started_at) * 1000))
        span.set_attribute("voice.first_audio_ms", ms)
        span.set_attribute("voice.first_audio_target_met", ms < 500)
        span.add_event("voice.first_audio", {"latency_ms": ms})
