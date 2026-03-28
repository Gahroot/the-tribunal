# Human-in-the-Loop Nudge System

## What You Asked For
A system where the AI CRM proactively sends SMS nudges to **you** (the human operator) — not just for issues, but for relationship-building reminders like birthdays, anniversaries, "send a handwritten card", etc. You want to configure which human(s) receive these nudges per-account/workspace, with your phone number as the delivery channel.

---

## What Already Exists

| Capability | Status | Where |
|---|---|---|
| **User phone numbers** | ✅ Exists | `User.phone_number` field, editable in Settings > Profile |
| **SMS notification preferences** | ✅ Exists | `User.notification_sms` toggle |
| **Telnyx SMS sending** | ✅ Exists | `TelnyxSMSService` in `backend/app/services/telephony/telnyx.py` |
| **SMS to workspace members** | ✅ Exists | `lead_form.py` already loops workspace members and texts those with `notification_sms=True` and a phone number |
| **Push notifications** | ✅ Exists | `PushNotificationService` with Expo Push API |
| **Automation worker** | ✅ Exists | Trigger-based automations with `send_sms`, `apply_tag`, `enroll_campaign` actions |
| **Background worker pattern** | ✅ Exists | `BaseWorker` with poll loop, used by 15+ workers |
| **Contact date fields (birthday, anniversary)** | ❌ Missing | Contact model has no date-type custom fields |
| **Nudge/reminder model** | ❌ Missing | No concept of "nudge to human" exists |
| **AI-generated relationship suggestions** | ❌ Missing | Improvement suggestions are prompt-only, not relationship-focused |
| **Per-contact human assignment** | ❌ Missing | No "account owner" or "assigned human" concept on contacts |

---

## Architecture Options

### Option A: "Nudge Worker" — New Dedicated System (Recommended)

Build a self-contained nudge system with its own model, worker, and UI. This is the cleanest approach and avoids overloading the existing automation system.

**New pieces:**
1. **`HumanNudge` model** — stores generated nudges (type, contact, message, priority, delivery status)
2. **`ContactDate` model** (or add JSONB `important_dates` field to Contact) — birthdays, anniversaries, custom dates
3. **`NudgeWorker`** — background worker that scans contacts daily for upcoming dates and generates nudges
4. **`NudgeDeliveryService`** — sends SMS to the assigned human(s) via Telnyx
5. **Per-contact or per-workspace human assignment** — who gets the nudge
6. **Nudge settings UI** — configure your phone number, which nudge types you want, lead time (e.g., "3 days before birthday")
7. **Nudge inbox/dashboard** — see pending nudges, mark as done, snooze

**Nudge types (day-1):**
- 🎂 Birthday coming up
- 💍 Anniversary coming up
- 📝 "Send a handwritten card" (triggered X days before a date)
- 🔄 Haven't talked in N days (relationship cooling)
- 📅 Follow-up reminder (N days after last conversation)
- 🏆 Deal milestone (opportunity stage change)

**How it works:**
```
Daily scan (NudgeWorker)
  → Find contacts with dates in the upcoming window
  → Generate HumanNudge rows
  → NudgeDeliveryService sends SMS to assigned human(s)
  → "Hey Nolan — Sarah Chen's birthday is in 3 days. Consider sending a handwritten card! 🎂"
```

**Pros:** Clean separation, purpose-built for this use case, easy to extend with AI-generated suggestions later  
**Cons:** More new code, new migration, new UI section

---

### Option B: Extend Existing Automations

Add a new trigger type (`date_approaching`) and a new action type (`notify_human`) to the existing automation system.

**Changes:**
1. Add `important_dates` JSONB field to Contact model
2. Add `date_approaching` trigger type to `AutomationWorker`
3. Add `notify_human` action type that texts workspace members instead of the contact
4. Users create automations like: "When birthday is 3 days away → notify_human with message template"

**Pros:** Leverages existing automation infrastructure, less new code  
**Cons:** Automations are designed for contact-facing actions — bolting human notification onto them is architecturally awkward. No good place for a nudge inbox/history. Users have to manually create each nudge rule as an automation.

---

### Option C: Hybrid — Nudge Model + Automation Triggers

Same as Option A but nudges can also be triggered from automations (e.g., "when contact tagged 'VIP' → create nudge for human"). Best of both worlds but more work.

---

## My Recommendation: Option A (Nudge Worker)

Here's why:
- **This is a distinct domain** — "notify the human about a relationship opportunity" is fundamentally different from "send an SMS to a contact." It deserves its own model.
- **You want an inbox feel** — a place to see all pending nudges, act on them, dismiss them. Automations don't have that.
- **It's extensible** — later you can plug in AI that analyzes conversations and generates nudges like "This contact mentioned they're moving offices — offer to help" or "This contact hasn't responded in 2 weeks, they might be going cold."
- **The SMS delivery is trivial** — the pattern already exists in `lead_form.py` (loop workspace members, send Telnyx SMS to those with `notification_sms` enabled and a phone number). We just reuse it.

---

## Detailed Implementation Plan (Option A)

### Phase 1: Data Foundation

**1a. Migration: Add `important_dates` to Contact**
- File: new Alembic migration
- Add `important_dates: JSONB` column to `contacts` table
- Structure: `{"birthday": "1990-03-15", "anniversary": "2020-06-20", "custom": [{"label": "Contract Renewal", "date": "2026-08-01"}]}`
- Update `Contact` model in `backend/app/models/contact.py`
- Update contact schemas in `backend/app/schemas/contact.py`

**1b. New model: `HumanNudge`**
- File: `backend/app/models/human_nudge.py`
- Fields: `id`, `workspace_id`, `contact_id`, `nudge_type` (birthday, anniversary, follow_up, cooling, custom), `title`, `message`, `suggested_action` (send_card, call, text, email), `priority` (low/medium/high), `due_date`, `status` (pending, sent, acted, dismissed, snoozed), `snoozed_until`, `delivered_via` (sms, push, both), `delivered_at`, `acted_at`, `assigned_to_user_id` (nullable — defaults to all workspace members), `source_date_field`, `created_at`

**1c. Migration: Create `human_nudges` table**

**1d. Workspace nudge settings** (stored in `workspace.settings` JSONB)
- `nudge_settings.enabled`: bool
- `nudge_settings.lead_days`: int (how many days before a date to nudge, default 3)
- `nudge_settings.nudge_types`: list of enabled types
- `nudge_settings.delivery_channels`: ["sms", "push"]
- `nudge_settings.quiet_hours`: {start: "22:00", end: "08:00"}

### Phase 2: Backend Logic

**2a. `NudgeGeneratorService`**
- File: `backend/app/services/nudges/nudge_generator.py`
- Scans contacts with `important_dates` for upcoming dates within the lead window
- Generates `HumanNudge` rows (idempotent — won't create duplicates for same contact+date+year)
- Generates relationship-cooling nudges (no conversation in N days for active contacts)

**2b. `NudgeDeliveryService`**
- File: `backend/app/services/nudges/nudge_delivery.py`
- Takes a `HumanNudge`, resolves the target human(s):
  - If `assigned_to_user_id` is set → that user
  - Else → all workspace members with `notification_sms=True`
- Sends SMS via Telnyx (reuse pattern from `lead_form.py`)
- Sends push notification via `PushNotificationService`
- Marks nudge as `sent` with `delivered_at`

**2c. `NudgeWorker`**
- File: `backend/app/workers/nudge_worker.py`
- Extends `BaseWorker`, polls every 60 minutes (not 60 seconds — nudges are daily)
- Calls `NudgeGeneratorService` then `NudgeDeliveryService`
- Respects quiet hours

**2d. API routes**
- File: `backend/app/api/v1/nudges.py`
- `GET /workspaces/{id}/nudges` — list nudges (filterable by status, type)
- `GET /workspaces/{id}/nudges/stats` — counts by status
- `PUT /nudges/{id}/act` — mark as acted on
- `PUT /nudges/{id}/dismiss` — dismiss
- `PUT /nudges/{id}/snooze` — snooze until date
- `GET /workspaces/{id}/nudge-settings` — get settings
- `PUT /workspaces/{id}/nudge-settings` — update settings

### Phase 3: Frontend

**3a. Contact detail: Important dates editor**
- Add a "Dates" section to the contact detail view
- Birthday picker, anniversary picker, add custom dates
- Calls updated contact API to save `important_dates`

**3b. Nudge settings page**
- New tab in Settings or standalone page
- Configure: enabled, lead days, nudge types, delivery channels, quiet hours
- "Your phone number" display (links to profile settings)

**3c. Nudge inbox/dashboard**
- New page at `/nudges` or section in dashboard
- Cards showing pending nudges with contact info, suggested action, due date
- Actions: Mark Done, Dismiss, Snooze
- Filter by type, status

### Phase 4: Polish & Extension

- AI-generated nudges (analyze conversation sentiment, detect milestones mentioned in calls)
- "Per-contact human assignment" (account owner field on Contact)
- Nudge templates (customizable message formats)
- Weekly nudge digest SMS ("You have 5 nudges this week: 2 birthdays, 1 follow-up...")

---

## Effort Estimate

| Phase | Files | Estimate |
|---|---|---|
| Phase 1: Data | 5-6 files (model, schema, migration, contact update) | ~2 hours |
| Phase 2: Backend | 5-6 files (services, worker, API routes, schemas) | ~3 hours |
| Phase 3: Frontend | 4-5 files (settings, inbox, contact dates) | ~3 hours |
| **Total** | **~15 files** | **~8 hours** |

---

## What Do You Want?

1. **Full Option A** — Build the complete nudge system (recommended)
2. **Quick MVP** — Just add `important_dates` to contacts + a nudge worker that texts you, skip the UI inbox for now (faster, ~4 hours)
3. **Option B** — Extend automations instead (less code but less powerful)
4. **Something else** — Different scope or priority

Let me know which direction and I'll start building.
