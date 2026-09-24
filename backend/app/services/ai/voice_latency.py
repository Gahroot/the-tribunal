"""Server-side voice budget, not a measurement of caller-heard PSTN latency.

One greeting and one turn may be pending. Timers never perform network I/O;
OTLP uses the existing batch exporter and Prometheus is scraped separately.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import structlog
from opentelemetry import trace
from opentelemetry.trace import Span, set_span_in_context

from app.core.metrics import voice_audio_latency_ms, voice_audio_latency_regressions_total

TARGET_MS = 500
ALERT_MS = 1000
logger = structlog.get_logger(__name__)
_TRACER = trace.get_tracer(__name__)


@dataclass
class _Pending:
    started: float
    span: Span
    timer: asyncio.TimerHandle | None = None
    alerted: bool = False


class VoiceLatencyBudget:
    """Owned by the call trace; cancelled on barge-in and closed with the call."""

    def __init__(self, root: Span, provider: str) -> None:
        self.root = root
        self.provider = (
            provider if provider in {"openai", "grok", "elevenlabs", "live"} else "unknown"
        )
        self.pending: dict[str, _Pending] = {}
        self.closed = False

    def start(self, phase: str, started: float | None = None) -> None:
        if self.closed or phase in self.pending:
            return
        # Internal bounded enum only; never accept a provider event as a label.
        if phase not in {"greeting", "turn", "response"}:
            return
        span = _TRACER.start_span(
            "voice.audio_latency",
            context=set_span_in_context(self.root),
            attributes={
                "voice.provider_path": self.provider,
                "voice.latency.phase": phase,
                "voice.latency.target_ms": TARGET_MS,
                "voice.latency.alert_ms": ALERT_MS,
            },
        )
        pending = _Pending(time.monotonic() if started is None else started, span)
        self.pending[phase] = pending
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        delay = max(0, ALERT_MS / 1000 - (time.monotonic() - pending.started))
        pending.timer = loop.call_later(delay, self._alert, phase)

    def _alert(self, phase: str) -> None:
        pending = self.pending.get(phase)
        if pending is None or pending.alerted:
            return
        pending.alerted = True
        voice_audio_latency_regressions_total.labels(self.provider, phase).inc()
        pending.span.add_event("voice.latency.regression", {"threshold_ms": ALERT_MS})
        # No transcripts, credentials, phone numbers, or unbounded metric labels.
        logger.warning(
            "voice_latency_budget_exceeded",
            provider_path=self.provider,
            phase=phase,
            threshold_ms=ALERT_MS,
            trace_id=format(self.root.get_span_context().trace_id, "032x"),
        )

    def audio_sent(self) -> None:
        for phase, pending in list(self.pending.items()):
            elapsed = max(0.0, (time.monotonic() - pending.started) * 1000)
            if elapsed > ALERT_MS:
                self._alert(phase)
            voice_audio_latency_ms.labels(self.provider, phase).observe(elapsed)
            pending.span.set_attribute("voice.latency.ms", elapsed)
            pending.span.set_attribute("voice.latency.target_met", elapsed < TARGET_MS)
            self._finish(phase, "audio_sent")

    def _finish(self, phase: str, outcome: str) -> None:
        pending = self.pending.pop(phase, None)
        if pending is None:
            return
        if pending.timer is not None:
            pending.timer.cancel()
        pending.span.set_attribute("voice.latency.outcome", outcome)
        pending.span.end()

    def interrupt(self) -> None:
        self._finish("turn", "interrupted")
        self._finish("response", "interrupted")

    def close(self) -> None:
        self.closed = True
        for phase in list(self.pending):
            self._finish(phase, "no_audio")
