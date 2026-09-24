# Voice audio latency budget

Target: **<500 ms**. Warn at **1 s**; never drop a call to satisfy a latency SLO.
The existing task-19 call trace owns the measurements and cancels watchdogs on exit.

## Measurement boundaries

- `greeting`: bridge entry to first successful outbound Telnyx media-frame send.
  Includes call-context lookup, provider setup, and greeting gating.
- `turn`: receipt of provider `input_audio_buffer.speech_stopped` to first successful
  outbound media-frame send, for OpenAI Realtime, Grok, and Grok + ElevenLabs.
  Provider endpointing and transport before speech-stopped receipt are not measured.
- `response`: GPT Live `turn.created` to outbound media frame. Live currently exposes
  no reliable speech-end event; **this is not comparable to turn latency**.
- Barge-in cancels a pending turn rather than attributing interrupted audio to it.
  Tool continuation responses do not reset the speech-end clock.
- These are server-side timings, not proof of caller-heard latency. Carrier buffering,
  network transit, and actual audible speech onset require a dual-channel call recording.

Each `voice.audio_latency` span is a child of the task-19 call trace, with bounded
`voice.provider_path`, phase, elapsed milliseconds, target-met flag, and outcome.
Unanswered turns end as `no_audio`, not a fabricated zero. Timers emit a warning even
if audio never arrives. No transcript or credentials enter these measurements.

## Alerts and dashboards

`voice_latency_budget_exceeded` is emitted once per slow measurement, with a trace ID,
provider path and phase. It works even when OTLP export is disabled. Prometheus metrics:

- `voice_audio_latency_ms{provider_path,phase}`: histogram with 500/1000/2000 ms buckets.
- `voice_audio_latency_regressions_total{provider_path,phase}`: includes no-audio waits.

Load `latency-alerts.yml` into the deployment's Prometheus `rule_files` and route warning
alerts through its Alertmanager. This repository does not provision an Alertmanager;
shipping the file does not activate external paging. Immediate structured warnings are
active in application code. Example p95 query:

```promql
histogram_quantile(0.95, sum by (le, provider_path, phase) (rate(voice_audio_latency_ms_bucket[5m])))
```

## Hot-path guard

Audio and normal turn events use persistent OpenAI/Grok WebSockets, persistent
ElevenLabs TTS WebSockets, or GPT Live WebRTC/data channels. Do not add HTTP calls
for metrics, token refresh, configuration lookup, or audio per turn. OpenAI ephemeral
credential minting and provider setup happen at connection time. Explicit business
tools (booking/payment/transfer) still legitimately use HTTP; removing these changes
call behavior. OTLP remains batched, Prometheus pull-based, and watchdogs do no HTTP.
The relay regression tests forbid HTTP requests while exercising repeated turn events
and outbound media delivery for all four session classes.

## Sources and evidence limits

Reviewed 2026-09-24:

- [OpenBenchmarks](https://openbenchmarks.com/voice-agent-latency/voice-agent-latency-comparison):
  1,296 ms is the lowest platform median in this comparison, not an industry-wide median.
  It measures speech end to reply onset in dual-channel phone recordings, and explains
  why roughly two-second pauses cause callers to speak again.
- [ElevenLabs evaluation framework](https://elevenlabs.io/blog/voice-agent-evaluation-framework-6-pillars-explained):
  recommends time-to-first-audio below 500 ms and inspecting tail latency.
- Steroids corpus search for `speech_stopped` found the persistent receive-loop event
  dispatch in `livekit/agents`, `livekit-agents/livekit/agents/llm/_realtime/openai.py`.
  Used to cross-check the event boundary, not to claim caller-heard timing.

Local tests prove boundary accounting, alerts, cleanup, and successful Telnyx-frame
measurement using in-memory transports. They do not establish real provider/PSTN
latency or demonstrate that production meets the 500 ms target.
