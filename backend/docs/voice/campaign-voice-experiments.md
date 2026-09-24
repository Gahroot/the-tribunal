# Natural speech and campaign voice experiments

## Natural speech

Grok, OpenAI Realtime, ElevenLabs, and GPT Live now share plain-text realism guidance at initial configuration and prompt rebuilds. It asks for short sentences (about 25 words), occasional turn-start fillers, fillers before long/unfamiliar words, and quick restarts. The 5–10% disfluency figure is context, not a quota. Names, prices, numbers, disclosures, consent, tool use, and IVR navigation take priority. No SSML or bracketed sound effects are inserted.

These are generation instructions, not a guarantee of audio quality or a measured filler rate. Listen to authorized test calls before rollout.

## Configure an experiment through the voice-campaign API

Add `voice_experiment` to `POST /api/v1/workspaces/{workspace_id}/voice-campaigns`, or `PUT .../{campaign_id}` **before launch**. Other existing required campaign fields are unchanged. No dashboard editor is added by this change.

```json
{
  "voice_experiment": {
    "provider": "openai",
    "variants": [
      {"id": "a", "voice_id": "alloy", "gender": "neutral", "accent": "American", "speed": 0.9},
      {"id": "b", "voice_id": "shimmer", "gender": "female", "accent": "British", "speed": 1.1}
    ]
  }
}
```

- Opt-in; omitted/null preserves single-voice behavior.
- Two to six equal-weight variants. Provider must match the voice agent.
- Gender is a **catalog voice label**, not a synthetic pitch/gender switch. Choose the corresponding provider voice ID; there is no automated voice cloning or demographic targeting.
- Realtime providers receive accent instructions. ElevenLabs accents must come from the selected catalog voice; changing an accent label alone does not change its sound.
- OpenAI and ElevenLabs receive native speed settings (experiment range 0.7–1.2). Grok and GPT Live receive pace instructions; their numeric speeds are approximate, not acoustic measurements.
- Known OpenAI/Grok/Live IDs are validated to prevent silent fallback. ElevenLabs account-specific IDs must be verified in that account before launch.
- Contact assignment hashes campaign ID + contact ID. It is independent of order and demographics, approximately balanced, stable across retries, and persisted as a provider/voice/trait/speed snapshot before the call transaction completes.
- Shared agent voice settings are never overwritten. Call-local overrides are applied to a detached agent when the bridge loads the campaign call.
- Experiment configuration and its campaign agent cannot change after launch, including while paused. Create a new campaign to compare a new set of variants. Keep the underlying agent prompt/tools and outreach settings unchanged during the test; disable concurrent prompt experiments to isolate voice effects.

## Read conversion results

`GET .../{campaign_id}/analytics` includes `voice_experiment`:

- `metric`: `campaign_appointment_booking`
- `denominator`: `assigned_contacts`
- Each variant reports `assigned_contacts`, `converted_contacts`, and `conversion_rate` (percentage, 0 for an empty cohort).

A conversion is at least one appointment attributed to the **same campaign, contact and workspace**, created after assignment. Multiple appointments count once. SMS fallback bookings count as campaign conversions; cancelled appointments remain historical bookings. Unanswered calls and failed dials remain in the denominator (intent-to-treat). This is not answer rate, revenue, or attended-appointment conversion.

No automatic winner is selected. Compare cohorts after equal observation time and enough conversions; early differences are not evidence of uplift. Do not delete/re-enroll campaign contacts during measurement, since existing campaign-contact deletion also removes their assignment history.

## Migration and verification

`20260924_voice_experiments` adds two nullable JSONB columns, without a backfill or destructive upgrade. Apply with `uv run alembic upgrade head` after a backup and local migration rehearsal. Downgrade deletes experiment configuration/assignment data; do not downgrade a live experiment.

Automated checks cover schema rejection, stable/balanced assignments, all-provider prompt guidance, OpenAI and ElevenLabs payload speed, launch freeze, and workspace-scoped unique-contact conversion SQL. API authorization was probed on a local server with workers disabled (401, no data). Authenticated ASGI tests verify analytics JSON and invalid-speed rejection using a mocked database.

Verification: 654 backend tests passed (four deprecation/mock cleanup warnings), Ruff passed, targeted mypy passed, and frontend `npm run typecheck` passed. Offline `alembic upgrade 20260923_model_configs:20260924_voice_experiments --sql` produced only the two nullable additions plus migration-version bookkeeping. Commit review uses `git diff --cached`; no generated artifacts are hand-edited.

Local PostgreSQL and Docker were unavailable during implementation. Database migration execution, seeded conversion aggregation against PostgreSQL, authenticated database-backed API responses, worker dialing, and live audio were **not verified**. No real calls or production changes were made. The generated OpenAPI contract and TypeScript client include the experiment configuration/results.

## Research (24 September 2026)

- [Rime filler guide](https://www.rime.ai/resources/how-to-add-natural-filler-words-to-tts): plain-text fillers, turn starts/before long words, 5–10% context, short sentences.
- [Retell basic settings](https://docs.retellai.com/build/single-multi-prompt/configure-basic-settings): catalog voice/accent selection and voice speed controls.
- [ElevenLabs speed control](https://elevenlabs.io/docs/eleven-agents/customization/voice/speed-control): supported 0.7–1.2 range.
- Connected Steroids corpus: `livekit/agents`, commit `d8405f132e1bd960f298190c18daf81ffc1faf45`, `livekit-plugins/livekit-plugins-elevenlabs/livekit/plugins/elevenlabs/tts.py`: `VoiceSettings.speed`. The standalone `steroids` CLI was not installed.
- Installed OpenAI SDK: `types/realtime/realtime_audio_config_output_param.py`: `audio.output.speed`, native 0.25–1.5 range and turn-boundary restriction.

Engineering guidance, not legal advice: realism never authorizes impersonation, undisclosed AI calling, bypassing consent, or unauthorized use of a cloned voice. Existing outreach and opt-out gates remain in place.
