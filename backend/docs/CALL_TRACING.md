# Voice call tracing

The existing OpenTelemetry batch exporter emits one `voice.call` span for each
media bridge attempt (including rejected and failed bridges), `voice.llm` spans
from response/turn creation to completion for OpenAI Realtime, Grok,
Grok+ElevenLabs, and Live turns, `voice.tts` spans for ElevenLabs text submissions,
`voice.tool` spans for voice-tool executions, and `telephony.telnyx.webhook` spans
for Telnyx voice events after signature verification. Independent webhooks and
the media bridge use a deterministic trace ID derived from Telnyx
`call_control_id` (SHA-256); search by `call.id` to find
all hops. The booked appointment's Cal.com `booking_uid` is on the successful
`book_appointment` tool span. No transcript, prompts, phone numbers, tool inputs,
or tool outputs are exported by these spans. The existing HTTP/DB auto-instrumentation
may export other metadata: apply the collector's data-retention and access controls.

`voice.first_audio_ms` is measured from arrival at the media bridge to the first
outbound Telnyx audio frame; `voice.first_audio_target_met` tests <500 ms.
This is bridge-start latency, **not** caller-end-of-speech to audible playback.
The requested 1,296 ms industry median is an external comparison supplied in the
feature brief, not measured here; only compare equivalent measurement windows.
Async relay tasks share a once-only audio marker and report to the call span.
`voice.tool_success_rate` and `voice.tool_success_target_met` test >95% across
executed voice tools. `voice.estimated_cost_usd` sums priced LLM responses,
ElevenLabs text submissions, and the media bridge's Telnyx duration estimate.
It is emitted only when every component has known pricing; otherwise
`voice.cost_complete=false` and **no total is published**. OpenAI prices come
from workspace model configuration; Grok token prices require
`VOICE_GROK_INPUT_USD_PER_MILLION` and `VOICE_GROK_OUTPUT_USD_PER_MILLION`.
ElevenLabs needs `VOICE_ELEVENLABS_USD_PER_1000_CHARS`; Live reports subscription
allowance usage, not a per-call charge, so its cost remains unknown. Telnyx requires `VOICE_TELNYX_USD_PER_MINUTE`. These are
operator-supplied **estimates**, not provider invoices: actual carrier billing,
fees, transfers, and media after the bridge ends are not known here. A call
without a media bridge has webhook spans but no priced total. Outbound call
initiation has a `telephony.telnyx.dial` span in the provider call's trace;
failed dials without a provider call ID use the local message ID instead.

## Storage and Langfuse setup

Reuse the existing bounded OTLP batch exporter; no additional SDK, table, or
synchronous database write is needed on the audio path. Export is off unless
`OTEL_EXPORTER_OTLP_ENDPOINT` or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is set.
For Langfuse (hosted or self-hosted), configure deployment secrets:

```sh
OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://<your-host>/api/public/otel/v1/traces
```

Set `OTEL_EXPORTER_OTLP_TRACES_HEADERS` to an HTTP Basic Authorization header
using the base64-encoded `public-key:secret-key`, plus
`x-langfuse-ingestion-version=4` for real-time v4 ingestion. Never commit these
values. Signal-specific protocol settings take precedence over the general
`OTEL_EXPORTER_OTLP_PROTOCOL`; Langfuse does not accept gRPC.

LLM spans use `langfuse.observation.type=generation`, standard `gen_ai.usage.*`
token counts, and JSON `langfuse.observation.cost_details` for known estimated
costs. Tool spans use type `tool`, with error status for unsuccessful results.
Call/LLM/tool spans include `session.id` for grouping. Successful bookings carry
`appointment.booking_uid` and `langfuse.trace.metadata.booking_uid`, which join
to the appointment's Cal.com booking UID. Logs include the active `trace_id` and
`span_id`; error spans do not export exception messages or stack traces.

In the collector UI, group by trace ID (or filter `session.id` by the call ID),
inspect the `voice.call` metrics above, and expand LLM/tool/telephony spans for
latency. Search booking UID on tool metadata to trace a booked appointment back
to the call. Do not sum call-level totals and generation costs together: the
former already includes the latter. Calls that do not book have no booking UID.
No-tool calls omit success rate rather than falsely reporting 100%.

Without a collector spans are not retained locally. Provision access-controlled
storage and explicit retention at the collector before enabling production
export. The bounded batch queue may drop spans during collector outages or
abrupt process termination; tracing is diagnostic, not an invoicing ledger.

### Verification and research

`uv run --no-sync pytest tests/core/test_telemetry.py tests/services/ai/test_call_tracing.py`
checks real HTTP/protobuf export to a loopback collector, trace joins, async
first-audio tracking, tokens/cost mapping, tool outcomes, and booking linkage.
It does not prove production acoustic latency or hosted Langfuse delivery.

Pattern verified against [Langfuse OTEL ingestion documentation](https://langfuse.com/docs/opentelemetry/get-started)
and the refreshed Steroids corpus `langfuse/langfuse` source,
`packages/shared/src/server/otel/attributes.ts` (commit `ce4a1e9e`).
