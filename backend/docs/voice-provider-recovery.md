# Voice provider recovery

OpenAI, Grok and the Grok + ElevenLabs path surface fatal response errors,
rate limits, failed audio sends and terminated provider streams to the voice
bridge. Its health watcher also checks connection state every two seconds;
the provider WebSocket library's keepalive detects unresponsive peers. Connection
setup has a 20-second budget. Normal carrier stop/disconnect is not a recovery
signal. Provider cancellation and nonfatal protocol errors do not end a call.

## Callback routing

For a current outbound voice campaign attempt, the bridge locks the campaign
contact and commits `pending`, `last_call_status=provider_failure` and a retry
due in two minutes **before** attempting SMS or terminating the silent carrier
leg. The retry remains durable if SMS delivery fails or the callback worker is
down. Duplicate bridges and late hangup webhooks cannot reschedule that attempt.

The notification goes through `OutboundDeliveryService` with a stable key per
contact/attempt. Existing SMS consent, workspace opt-out, quiet hours and message
caps apply. A failed notification remains pending for the voice worker to retry.
The next successful dial clears the recovery marker. These are engineering
controls, not a legal compliance determination.

Recovery never resets the existing maximum call-attempt budget. It does not
revive paused campaigns, replied contacts or opted-out contacts. The worker
checks fresh workspace opt-outs before recovery dials. Calling windows take
precedence over two minutes. A missing, stale, malformed or future-dated worker
heartbeat changes the SMS to “when service is available during calling hours”
instead of making a two-minute promise. A heartbeat proves liveness, not that
all downstream dependencies are healthy.

A Redis cooldown, scoped by workspace and voice provider, pauses new campaign
dials for 120 seconds after failure. Redis health-check failure defers new
dials. A carrier HTTP 429 is persisted as `RATE_LIMITED` and requeues that contact
without counting it as an initiated call. Provider recovery is retried on the
same configured path; this does not hot-swap models in an active conversation.

## Scope and operations

Automatic SMS/callbacks require an existing outbound campaign attempt. Manual
and inbound calls are not silently enrolled into campaigns or given new consent.
A provider failure on those calls is detected and the unusable carrier leg is
closed, but no automated callback is created. Failed/exhausted attempts also
receive no false callback promise.

Run the voice campaign worker in the normal worker process (including when
`RUN_BACKGROUND_WORKERS=false` on API replicas). Watch these structured events:

- `voice_call_requeued`: persisted callback, with bounded failure reason.
- `voice_recovery_notification`: send result and callback worker liveness.
- `voice_campaign_provider_cooling_down`: no new dials on the affected path.
- `voice_provider_health_unknown`: Redis failure; new dials deferred.
- `voice_recovery_failed` / `voice_recovery_sms_deferred`: persistence or delivery
  trouble requiring attention. A database outage prevents durable callbacks;
  this is not hidden as a successful recovery.

Targeted regression check (no paid provider calls):

```sh
cd backend
uv run --no-sync pytest tests/services/ai/test_voice_recovery.py \
  tests/voice_ws/test_voice_bridge.py \
  tests/workers/test_voice_campaign_cadence.py \
  tests/workers/test_voice_campaign_worker_retryable.py
```

Tests exercise real provider event loops and bridge supervision using local
transports; persistence and delivery boundaries use fakes. Live carrier delivery,
Postgres locking across replicas, and real upstream outage drills require a
separate staging exercise.
