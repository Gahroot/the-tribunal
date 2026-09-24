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

Export is off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. To ingest into Langfuse,
use its OTLP HTTP endpoint and credentials (see Langfuse OpenTelemetry ingestion
instructions): set `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`,
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://<your-host>/api/public/otel/v1/traces`,
and `OTEL_EXPORTER_OTLP_HEADERS` to an HTTP Basic Authorization header for the
Langfuse public and secret keys. Set `OTEL_EXPORTER_OTLP_ENDPOINT` to the host as
well to enable the existing exporter; configure these as deployment secrets, not in
source. The batch exporter does not block audio on network I/O. Without a collector
spans are not retained locally. Provision access-controlled storage/retention at
the collector before enabling export of production calls.
