# Block Catalog — The Tribunal North Star

Every product capability in The Tribunal is described by a **block manifest** (`BLOCK.md`) so an AI agent can extract it into a new project. This catalog is the human-facing index of those manifests.

> **Generated file.** Rendered from `registry.json` by `scripts/blocks/build_registry.py`. Run `make blocks.check` to regenerate and validate; do not hand-edit.

See the [Agent Extraction Guide](./AGENT_EXTRACTION_GUIDE.md) for how an agent consumes these manifests, and the [BLOCK.md schema](./BLOCK_SCHEMA.md) for the frontmatter contract.

## Core — shared substrate

| Block | Summary | Depends on | Used by |
| --- | --- | --- | --- |
| [`core`](./core/BLOCK.md)<br>Core (Multi-Tenant Substrate) | The shared multi-tenant substrate every other block stands on — settings/config, the Fernet credential vault, workspace scoping, DB session + pagination, auth/DI dependencies, idempotency, the outbound HTTP provider layer, and the background-worker runtime. Depends on nothing; everything depends on it. | — | `agent-brain`, `appointments`, `automations`, `compliance`, `contacts`, `hitl`, `knowledge`, `lead-capture`, `messaging`, `offers`, `payments`, `reviews`, `short-links`, `voice`, `widget` |

## Tier A — headline / standalone-sellable

| Block | Summary | Depends on | Used by |
| --- | --- | --- | --- |
| [`lead-capture`](./lead-capture/BLOCK.md)<br>Lead Capture & Lead Magnets | Public lead-capture forms and gated lead magnets (quizzes, calculators, downloadable PDFs) that create contacts, fire speed-to-lead auto follow-up, and deliver magnet content by email. | `core`, `voice`, `agent-brain`, `offers`, `contacts`, `messaging` | `offers` |
| [`offers`](./offers/BLOCK.md)<br>Offers & Offer Builder | A guided builder for irresistible offers (value stack, pricing, guarantee, urgency, attached lead magnets) plus public opt-in offer pages that capture contacts and deliver the bundled lead magnets. | `core`, `agent-brain`, `lead-capture`, `contacts` | `agent-brain`, `knowledge`, `lead-capture`, `messaging` |
| [`reviews`](./reviews/BLOCK.md)<br>Reviews & Reputation | Requests, collects, and analyzes customer reviews per workspace; auto-sends SMS review requests after appointments, routes positive raters to public review sites, and tracks reputation/sender warming. | `core`, `voice`, `agent-brain`, `appointments`, `automations`, `compliance` | `appointments` |
| [`short-links`](./short-links/BLOCK.md)<br>Short Links & Click Tracking | Generates tracked short URLs for outbound SMS and records per-click events (count, last-clicked, IP/UA/referer), attributing clicks back to contacts and campaigns. | `core` | `messaging` |
| [`widget`](./widget/BLOCK.md)<br>Embeddable Chat & Voice Widget | A drop-in, unauthenticated website widget that lets visitors chat, voice-call, or text an AI agent; pairs a vanilla-TS embed bundle with public backend embed endpoints. | `core`, `voice`, `agent-brain`, `compliance` | — |

## Tier B — supporting capabilities

| Block | Summary | Depends on | Used by |
| --- | --- | --- | --- |
| [`appointments`](./appointments/BLOCK.md)<br>Appointments & Calendar | Books, reschedules, and tracks appointments per workspace via Cal.com; assigns bookable staff, resolves availability, sends SMS reminders, and runs no-show / never-booked re-engagement. | `core`, `contacts`, `messaging`, `voice`, `compliance`, `reviews` | `agent-brain`, `hitl`, `reviews` |
| [`messaging`](./messaging/BLOCK.md)<br>Messaging & Outbound Campaigns | SMS/iMessage campaigns, drip sequences, outbound missions, and the unified outbound delivery pipeline — renders templated messages, enforces compliance, dispatches via Telnyx or the mac-relay (iMessage), tracks delivery/replies, and runs AI fallback drafting. | `core`, `contacts`, `agent-brain`, `compliance`, `voice`, `offers`, `short-links`, `hitl` | `agent-brain`, `appointments`, `hitl`, `lead-capture`, `voice` |
| [`payments`](./payments/BLOCK.md)<br>In-Call Payments & Deposits | Stripe-backed in-call payment / deposit collection — creates hosted Checkout Sessions for an amount requested during a call, texts the secure link to the caller, reconciles session status, and notifies operators on payment. Distinct from SaaS subscription billing. | `core` | `agent-brain` |
| [`voice`](./voice/BLOCK.md)<br>Voice & Telephony (Crown Jewel) | The crown-jewel real-time AI voice/telephony stack — Telnyx voice + SMS, the OpenAI Realtime / ElevenLabs / Grok voice bridge, live-call supervision, inbound routing/screening, voicemail, missed-call textback, voice campaigns, roleplay, and call outcome/feedback capture. | `core`, `agent-brain`, `compliance`, `contacts`, `messaging`, `automations`, `hitl` | `agent-brain`, `appointments`, `automations`, `contacts`, `hitl`, `lead-capture`, `messaging`, `reviews`, `widget` |

## Tier C — peripheral / cross-cutting

| Block | Summary | Depends on | Used by |
| --- | --- | --- | --- |
| [`agent-brain`](./agent-brain/BLOCK.md)<br>Agent Brain (AI, Prompts & A/B Bandit) | The AI cognition layer — agent definitions/templates, prompt building, the real-time voice/text agent sessions (OpenAI Realtime / ElevenLabs / Grok), the CRM-assistant tool stack, IVR navigation, qualification, and the prompt-versioning + multi-armed-bandit A/B experimentation engine that learns which prompts and messages convert. | `core`, `appointments`, `automations`, `hitl`, `knowledge`, `messaging`, `offers`, `payments`, `voice` | `contacts`, `hitl`, `knowledge`, `lead-capture`, `messaging`, `offers`, `reviews`, `voice`, `widget` |
| [`automations`](./automations/BLOCK.md)<br>Automations (Event Bus & Rules Engine) | The workspace automation engine — an internal event bus (events.py) other blocks emit to, plus a trigger/condition/action rules engine that drains those events and runs operator-defined automations (send message, place call, tag, escalate) in the background. | `core`, `contacts`, `hitl`, `voice` | `agent-brain`, `knowledge`, `reviews`, `voice` |
| [`compliance`](./compliance/BLOCK.md)<br>Compliance & Rate Limiting | The messaging-safety substrate — opt-out enforcement (STOP/global opt-outs), outbound compliance checks, per-number rate limiting, reputation/warming, and bounce classification. A cross-cutting dependency that every voice/messaging send must pass through before dispatch. | `core` | `appointments`, `messaging`, `reviews`, `voice`, `widget` |
| [`contacts`](./contacts/BLOCK.md)<br>Contacts, Segments & Tags | The contact/lead system of record — CRUD, import, encrypted phone/email lookup, timelines, engagement scoring, AI qualification state, plus rule-based segments and tags. Its contact_filters engine is the shared audience-selection primitive used across campaigns and automations. | `core`, `agent-brain`, `voice` | `appointments`, `automations`, `hitl`, `lead-capture`, `messaging`, `offers`, `voice` |
| [`hitl`](./hitl/BLOCK.md)<br>Human-in-the-Loop (Approvals, Nudges & Autonomy) | The human-in-the-loop control plane for an AI agent — pending-action approval gating, operator command processing over SMS, the autonomy mandate/escalation policy, and proactive operator nudges generated by a library of pluggable strategies. A reusable HITL pattern, not CRM-specific. | `core`, `agent-brain`, `appointments`, `contacts`, `messaging`, `voice` | `agent-brain`, `automations`, `messaging`, `voice` |
| [`knowledge`](./knowledge/BLOCK.md)<br>Knowledge Base (RAG Retrieval) | Per-workspace knowledge base with document ingestion, chunking, embeddings, and hybrid (pgvector KNN + tsvector keyword) retrieval — the RAG layer the AI agent queries for grounded answers and the knowledge-search tool. | `core`, `agent-brain`, `automations`, `offers` | `agent-brain` |

## Dependency notes

`core` is the mandatory substrate — every block that owns a database table, uses workspace scoping, auth, encryption, or pagination declares `depends_on: [core, …]`.

The dependency graph contains **intentional cycles** that mirror real runtime import cycles (documented in each manifest's `extraction_notes`). They are reported, not treated as errors:

- `agent-brain` → `appointments` → `contacts` → `agent-brain`
- `agent-brain` → `appointments` → `contacts` → `voice` → `agent-brain`
- `contacts` → `voice` → `contacts`
- `contacts` → `voice` → `messaging` → `contacts`
- `agent-brain` → `appointments` → `contacts` → `voice` → `messaging` → `agent-brain`
- `voice` → `messaging` → `voice`
- `agent-brain` → `appointments` → `contacts` → `voice` → `messaging` → `offers` → `agent-brain`
- `voice` → `messaging` → `offers` → `lead-capture` → `voice`
- `agent-brain` → `appointments` → `contacts` → `voice` → `messaging` → `offers` → `lead-capture` → `agent-brain`
- `offers` → `lead-capture` → `offers`
- `contacts` → `voice` → `messaging` → `offers` → `lead-capture` → `contacts`
- `messaging` → `offers` → `lead-capture` → `messaging`
- `contacts` → `voice` → `messaging` → `offers` → `contacts`
- `agent-brain` → `appointments` → `contacts` → `voice` → `messaging` → `hitl` → `agent-brain`
- `appointments` → `contacts` → `voice` → `messaging` → `hitl` → `appointments`
- `contacts` → `voice` → `messaging` → `hitl` → `contacts`
- `messaging` → `hitl` → `messaging`
- `voice` → `messaging` → `hitl` → `voice`
- `contacts` → `voice` → `automations` → `contacts`
- `voice` → `automations` → `voice`
- `agent-brain` → `appointments` → `reviews` → `agent-brain`
- `appointments` → `reviews` → `appointments`
- `agent-brain` → `knowledge` → `agent-brain`

## All manifests

- [`agent-brain`](./agent-brain/BLOCK.md) — tier `C`, status `manifest`, extraction effort `high`; integrates `openai`, `elevenlabs`.
- [`appointments`](./appointments/BLOCK.md) — tier `B`, status `manifest`, extraction effort `medium`; integrates `cal.com`, `telnyx`.
- [`automations`](./automations/BLOCK.md) — tier `C`, status `manifest`, extraction effort `medium`.
- [`compliance`](./compliance/BLOCK.md) — tier `C`, status `manifest`, extraction effort `low`.
- [`contacts`](./contacts/BLOCK.md) — tier `C`, status `manifest`, extraction effort `medium`.
- [`core`](./core/BLOCK.md) — tier `core`, status `manifest`, extraction effort `low`.
- [`hitl`](./hitl/BLOCK.md) — tier `C`, status `manifest`, extraction effort `high`.
- [`knowledge`](./knowledge/BLOCK.md) — tier `C`, status `manifest`, extraction effort `medium`; integrates `openai`.
- [`lead-capture`](./lead-capture/BLOCK.md) — tier `A`, status `extracted`, extraction effort `high`; integrates `telnyx`, `resend`.
- [`messaging`](./messaging/BLOCK.md) — tier `B`, status `manifest`, extraction effort `high`; integrates `telnyx`, `mac-relay`.
- [`offers`](./offers/BLOCK.md) — tier `A`, status `manifest`, extraction effort `medium`.
- [`payments`](./payments/BLOCK.md) — tier `B`, status `manifest`, extraction effort `low`; integrates `stripe`.
- [`reviews`](./reviews/BLOCK.md) — tier `A`, status `extracted`, extraction effort `medium`; integrates `telnyx`.
- [`short-links`](./short-links/BLOCK.md) — tier `A`, status `extracted`, extraction effort `low`.
- [`voice`](./voice/BLOCK.md) — tier `B`, status `manifest`, extraction effort `high`; integrates `openai`, `elevenlabs`, `telnyx`, `mac-relay`.
- [`widget`](./widget/BLOCK.md) — tier `A`, status `extracted`, extraction effort `medium`; integrates `openai`, `telnyx`.

_Generated by `scripts/blocks/build_registry.py`. Source of truth: the `BLOCK.md` manifests; machine-readable index: `registry.json`._
