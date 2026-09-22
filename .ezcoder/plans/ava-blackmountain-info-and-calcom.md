# Ava: Black Mountain Solutions brief + Cal.com booking on production

## Goal

Give the production voice agent **Ava** (Railway backend) enough accurate, first-party
information about Black Mountain Solutions to hold a credible inbound/outbound call, and
turn on Cal.com so she can actually book an appointment on the same calendar an existing,
already-working agent books to.

## What the code says (verified in this checkout)

**Ava's voice runtime — to be confirmed against production.**
`backend/scripts/demo/seed_gpt_live_agent.py:38` seeds `"Ava | GPT Live"` with
`voice_provider="openai"`, `channel_mode="voice"`, `realtime_model=gpt-realtime-2.x`, and
that provider routes to `VoiceAgentSession` (`backend/app/services/ai/voice_agent.py:40`)
via `VoiceSessionFactory._create_openai_session` (`voice_session_factory.py:130`). The
production row may have been edited since, so step 0 reads Ava's actual `voice_provider`
first. It changes one thing only — see the prompt-injection note below; the Cal.com gate
is the same either way (`_should_enable_tools`, `voice_session_factory.py:293-312`, also
keys off `calcom_event_type_id` + the global API key).

**Booking gate on this path is the event type only.** `voice_agent.py:374-376` calls
`get_tools_from_agent_config(..., enable_booking=bool(agent.calcom_event_type_id))`.
So `check_availability` / `book_appointment` appear as soon as
`agent.calcom_event_type_id` is set — `enabled_tools` is *not* consulted for booking on
the OpenAI realtime path (it is for the text/SMS path, `text_response_generator.py:276-280`,
which requires `"book_appointment" in enabled_tools`). We will set both so voice, SMS and
the dashboard UI agree.

**Execution needs the global API key.** `base_tool_executor._validate_calcom_config`
(`backend/app/services/ai/base_tool_executor.py:57-63`) fails with "Cal.com API key not
configured" unless `settings.calcom_api_key` is set. The voice executor does **not** read
the per-workspace encrypted Cal.com credential (only the text executor does,
`text_tool_executor.py:460-490`). So `CALCOM_API_KEY` must exist in the Railway backend
env. `app/main.py:280` logs `missing_calcom_api_key` at startup when it doesn't.

**Prompt is the agent row, not a prompt version.** `voice_bridge.py:229-237` configures the
session with `agent.system_prompt`; the bandit only *stamps* `prompt_version_id` for
attribution (`call_context.py:48-73`). Editing `system_prompt` takes effect on the next call,
no deploy needed.

**Booking prompt instructions are NOT auto-injected on the OpenAI path.**
`voice_agent.py:372` passes `include_booking=False` to `VoicePromptBuilder`, so the shared
Cal.com behaviour block (`prompt_builder.py:589`) never lands. (The Grok and ElevenLabs
paths *do* inject it — `grok/session.py:194`, `elevenlabs_voice_agent.py:333`.) On the
OpenAI path Ava's booking rules — ask for email, only offer slots the tool returned,
confirm back — must be written into her own system prompt. Writing them in is safe on
either path, just redundant on Grok/ElevenLabs.

**Timezone comes from the workspace, default is Eastern.**
`call_context.py:212` reads `workspace.settings["timezone"]` and defaults to
`America/New_York`. There is no API/UI endpoint that writes that key
(`api/v1/settings.py` only exposes business hours, forwarding, etc.), so for a Utah-based
business it must be set in the DB or Ava will narrate slots in the wrong zone.

**Risk — sharing one event type ID inside a workspace breaks the webhook.**
`api/webhooks/calcom_handlers.py:110-117` looks the agent up with
`scalar_one_or_none()` on `(workspace_id, calcom_event_type_id)`. Two agents in the same
workspace with the same event type ID raises `MultipleResultsFound`, so the
`BOOKING_CREATED` webhook 500s and the appointment never syncs into the CRM.
→ Preferred: duplicate the working agent's Cal.com event type inside Cal.com (same host =
still your calendar) and give Ava the new ID. Fall back to reusing the same ID only after
confirming no other agent in Ava's workspace holds it.

## Content to load into Ava (needs your confirmation)

`https://blackmountain.solutions` returns **HTTP 403** to automated fetches, so the facts
below come from search snippets of that page plus `blackmountainig.com`. They must not go
into a live agent's mouth unverified — please correct/approve before step 1.

| Fact | Source | Confirm? |
|---|---|---|
| Black Mountain Solutions (BMS), legal entity Limits LLC; boutique consulting firm; Utah; est. 2019 | site snippet | ✅/✏️ |
| Consulting arm of Black Mountain Investment Group (BMIG); BMIG is back-office/tech/consulting, not an adviser or broker-dealer | blackmountainig.com | ✅/✏️ |
| Focus areas: fund administration, real estate, technology/web, business consulting, SEO | site snippet | ✅/✏️ |
| Easefolio — proprietary fund-admin platform: NAV, reconciliation, reporting, compliance | site snippet | ✅/✏️ |
| Named work: The Food Nanny (Shopify rebuild + ongoing SEO), Advanced Window Products (SEO/lead gen), Luxury Rally Club (site + NFT), Anchor Mill Group (family-office platform) | site snippet | ✅/✏️ |
| Positioning/values: founded on family values by young Utah entrepreneurs; results-oriented, client-focused, integrity | site snippet | ✅/✏️ |
| People Ava may name (site testimonials reference **Sam** and **Elijah**) — roles/titles unknown | site snippet | ✏️ needed |
| Contact Ava may quote: 299 S Main St, 13th Floor, Salt Lake City UT 84111 · 435-800-5807 (this is BMIG's published contact) | blackmountainig.com privacy page | ✏️ needed |
| What the booked meeting actually is (name, length, who hosts it, what happens on it) | not public | ✏️ needed |

Anything you can't confirm gets left out. Ava's prompt will keep the existing guardrail —
never invent prices, availability, policies, or commitments — and will say a human will
follow up instead of guessing.

## How the change gets applied

A new idempotent ops script, run from a laptop against production exactly like the existing
precedent `backend/scripts/demo/update_demo_agents_calcom.py` (which resolves
`DATABASE_PUBLIC_URL` → asyncpg, lines 25-30). Script over dashboard clicks because it is
reviewable, repeatable, and `--dry-run`-able; the same fields are also editable by hand in
the dashboard (Prompt tab, Tools tab → "Appointment Booking", Advanced tab → "Cal.com Event
Type ID") if you prefer to do it in the UI after reviewing the generated prompt.

You will need to supply: the Railway `DATABASE_PUBLIC_URL`, Ava's `public_id` (or workspace
+ name), and the `public_id` of the agent already wired to your calendar.

## Verification

- Local: seed a copy of Ava in the dev DB, run the script against it, then
  `.ezcoder/eyes/http.sh http://localhost:8000/api/v1/agents/<public_id> GET -H "Authorization: Bearer <token>"`
  and confirm `calcom_event_type_id`, `enabled_tools`, `tool_settings`, `system_prompt`.
- Local behaviour: a pytest case asserting `get_tools_from_agent_config` exposes
  `check_availability` + `book_appointment` for the post-change agent shape.
- Production: script `--dry-run` diff first, then apply, then re-read the agent through the
  dashboard/API, place one real test call to Ava's number, book a slot, and confirm (a) the
  booking appears on the Cal.com calendar and (b) an `Appointment` row syncs — check
  `.ezcoder/eyes/logs.sh` equivalent on Railway (`railway logs`) for `booking_created` /
  absence of `MultipleResultsFound`.

## Out of scope

- Moving BMS knowledge into the knowledge-base documents + `search_knowledge` tool
  (`backend/app/api/v1/knowledge_documents.py`) — better long-term home for pricing/FAQ
  depth, but heavier; revisit once the prompt version proves itself.
- Multi-staff round-robin routing (`assignment_strategy`, `BookableStaff`) — Ava stays on
  `single`.
- Any change to Telnyx numbers, billing, or other agents' configuration.

## Steps

0. Read Ava's production agent row (`voice_provider`, `channel_mode`, `enabled_tools`,
   `calcom_event_type_id`, current `system_prompt`) and report it, so the plan's
   assumptions are checked against reality before anything is written.
1. Confirm the fact table above with you (approve/correct each row, supply Sam/Elijah roles,
   the meeting definition, and which phone/address Ava may quote); drop every unconfirmed claim.
2. Decide and record the calendar target: read the working agent's `calcom_event_type_id`
   from production, and either clone that Cal.com event type for Ava (preferred) or confirm
   no other agent in Ava's workspace already uses that ID before sharing it.
3. Confirm `CALCOM_API_KEY` is present on the Railway backend service (`railway variables`,
   or Railway startup logs showing no `missing_calcom_api_key` warning); stop and report if absent.
4. Write Ava's new system prompt as a reviewable constant: identity + BMS company/team brief
   (confirmed facts only), the single goal of booking the meeting, the explicit booking flow
   (qualify → `check_availability` → collect name + email → `book_appointment` → confirm
   date/time back), and the existing no-invention guardrails.
5. Add `backend/scripts/ops/configure_ava_blackmountain.py`: resolves the agent by
   `--agent <public_id>` (or `--workspace` + `--name`), refuses to touch another workspace,
   supports `--copy-from <public_id>` / `--event-type-id`, `--dry-run`, and prints a
   before/after diff of every field it writes.
6. In that script, set `calcom_event_type_id`, `assignment_strategy="single"`, merge
   `enabled_tools` with `bookings`, `check_availability`, `book_appointment`, set
   `tool_settings["bookings"] = ["check_availability", "book_appointment", "list_appointments"]`,
   and write the new `system_prompt` (only with an explicit `--overwrite-prompt` flag so a
   re-run never silently clobbers dashboard edits).
7. Add an optional `--timezone America/Denver` flag that writes `workspace.settings["timezone"]`,
   since no API exposes that key and the default is `America/New_York`.
8. Add pytest coverage under `backend/tests/` asserting the resulting agent shape exposes the
   booking tools via `get_tools_from_agent_config` and that the text path's
   `"book_appointment" in enabled_tools` gate is satisfied.
9. Run `make ci.backend`; seed a local Ava, apply the script locally, and verify the agent
   payload with `.ezcoder/eyes/http.sh`.
10. Run the script against production with `--dry-run`, review the diff with you, then apply.
11. Place a live test call to Ava's production number, book a slot end-to-end, and confirm the
    Cal.com booking plus the synced `Appointment` row and clean Railway logs.
12. Report the final production configuration (event type ID, tools, timezone) and anything
    Ava was deliberately left unable to answer.
