# Trib CLI — Comprehensive Implementation Plan

## Overview

Build `trib` — a Go CLI at `/home/groot/trib-cli` that gives AI agents full control over The Tribunal AI CRM. Follows the exact architecture of `/home/groot/pocket-agent-cli`: Cobra framework, stdlib HTTP, flat JSON config at `~/.config/trib/config.json`, LLM-friendly JSON output, `trib commands` self-discovery.

**Module path:** `github.com/unstablemind/trib`

## Architecture

```
trib-cli/
├── cmd/trib/main.go                    # Entry point
├── go.mod / go.sum
├── internal/
│   ├── cli/
│   │   ├── root.go                     # Root cobra command + global flags
│   │   └── commands/                   # Group wiring + commands index
│   │       ├── commands.go             # `trib commands` — LLM command index
│   │       ├── config.go              # `trib config` — get/set/list/path
│   │       ├── setup.go               # `trib setup` — connection test + guide
│   │       ├── contacts.go            # wires contacts package
│   │       ├── conversations.go       # wires conversations package
│   │       ├── agents.go              # wires agents package
│   │       ├── campaigns.go           # wires campaigns package
│   │       ├── calls.go               # wires calls package
│   │       ├── appointments.go        # wires appointments package
│   │       ├── offers.go              # wires offers package
│   │       ├── pipeline.go            # wires pipeline package
│   │       ├── phone.go               # wires phone package
│   │       ├── dashboard.go           # wires dashboard package
│   │       ├── admin.go               # wires admin package
│   │       └── content.go             # wires content package
│   ├── common/
│   │   ├── config/config.go           # Config store (~/.config/trib/config.json)
│   │   └── api/client.go             # Shared HTTP client + auth + workspace URL builder
│   ├── contacts/contacts.go           # Contact CRUD, search, filter, import, send-message, qualify, bulk ops
│   ├── conversations/conversations.go # List, get, send, AI toggle/pause/resume, followup
│   ├── agents/agents.go               # Agent CRUD, prompt versions, suggestions, embed settings
│   ├── campaigns/
│   │   ├── sms.go                     # SMS campaign lifecycle
│   │   ├── voice.go                   # Voice campaign lifecycle
│   │   └── reports.go                 # Campaign reports
│   ├── calls/calls.go                 # Initiate, list, hangup, outcomes, feedback
│   ├── appointments/appointments.go   # CRUD, stats, sync, reminders
│   ├── offers/offers.go               # Offer CRUD, generate, lead magnets
│   ├── pipeline/pipeline.go           # Pipelines, stages, opportunities, line items
│   ├── phone/phone.go                 # Phone number search, purchase, release, sync
│   ├── dashboard/dashboard.go         # Dashboard stats
│   ├── admin/
│   │   ├── integrations.go            # Integration CRUD + test
│   │   ├── automations.go             # Automation CRUD + toggle
│   │   ├── workspaces.go              # Workspace CRUD
│   │   ├── lead_sources.go            # Lead source CRUD
│   │   ├── scraping.go                # Lead scraping + find-leads-ai
│   │   └── invitations.go             # Invitation management
│   └── content/
│       ├── tags.go                     # Tag CRUD + bulk
│       ├── segments.go                 # Segment CRUD + resolve
│       ├── templates.go               # Message template CRUD
│       └── tests.go                   # Message test A/B lifecycle
├── pkg/output/output.go               # Shared JSON/text/table formatter (copy from pocket)
└── CLAUDE.md                          # Dev instructions
```

## Backend Changes Required

### Task 0: API Key Authentication System

The backend currently only supports JWT (short-lived access + refresh tokens). We need to add long-lived API keys that are workspace-scoped — perfect for CLI/agent use.

**New model:** `app/models/api_key.py`
```python
class APIKey(Base):
    __tablename__ = "api_keys"
    id: UUID (pk)
    workspace_id: UUID (FK workspaces.id)
    user_id: int (FK users.id) — who created it
    name: str — human label ("trib-cli", "pocket-agent")
    key_hash: str — bcrypt hash of the key
    key_prefix: str(8) — first 8 chars for identification (e.g. "trib_a1b2")
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
```

**New schema:** `app/schemas/api_key.py`
- `APIKeyCreate(name, expires_in_days: int | None)`
- `APIKeyResponse(id, name, key_prefix, is_active, last_used_at, created_at)` 
- `APIKeyCreated(id, name, key, key_prefix)` — only returned on create (plaintext key shown once)

**New endpoints:** `app/api/v1/api_keys.py` mounted at `/workspaces/{workspace_id}/api-keys`
- `POST /` — Create API key (returns plaintext key once)
- `GET /` — List API keys (redacted)
- `DELETE /{id}` — Revoke API key

**Auth dependency update:** `app/api/deps.py`
- Modify `get_current_user` to also check for `X-API-Key` header
- If present, hash it, look up in `api_keys` table, verify active + not expired
- Set `last_used_at`, return the associated user
- Also inject `workspace_id` from the API key so the CLI doesn't need to specify it separately (but we'll keep workspace_id in URL for consistency)

**Migration:** New alembic migration for `api_keys` table.

## CLI Tasks (in dependency order)

### Task 1: Project Scaffold + Config + Output

Initialize the Go project, set up the skeleton matching pocket-agent-cli patterns:
- `go.mod` with `github.com/unstablemind/trib`
- `cmd/trib/main.go`
- `internal/cli/root.go` — root command with `--output`, `--verbose` flags
- `internal/common/config/config.go` — config store with keys: `api_key`, `api_url`, `workspace_id`
- `pkg/output/output.go` — copy pocket's output package
- `internal/cli/commands/config.go` — `trib config set/get/list/path`
- `CLAUDE.md` with build/lint instructions

### Task 2: Shared API Client

`internal/common/api/client.go` — the backbone all commands use:
- `httpClient` with 30s timeout
- `func BaseURL() string` — reads `api_url` from config (default: `http://localhost:8000`)
- `func WorkspaceURL(path string) string` — builds `/api/v1/workspaces/{workspace_id}/path`
- `func Do(method, url string, body any, result any) error` — makes request with `X-API-Key` header
- `func Get(url string, result any) error`
- `func Post(url string, body any, result any) error`
- `func Put(url string, body any, result any) error`
- `func Delete(url string, result any) error`
- Error handling: decode JSON error body, surface message

### Task 3: Setup + Commands Index

- `internal/cli/commands/setup.go` — `trib setup` with connection test (`GET /health`), `trib setup show` with guide
- `internal/cli/commands/commands.go` — `trib commands` listing all available commands for LLM discovery

### Task 4: Dashboard

`internal/dashboard/dashboard.go`:
- `trib dashboard stats` — GET `/dashboard/stats`

### Task 5: Contacts

`internal/contacts/contacts.go` — the biggest command group:
- `trib contacts list` — with `--page`, `--limit`, `--status`, `--search`, `--tags`, `--sort`, `--qualified`, `--source`, `--score-min`, `--score-max`
- `trib contacts get [id]` 
- `trib contacts create` — with `--first-name`, `--last-name`, `--email`, `--phone`, `--company`, `--source`, `--notes`
- `trib contacts update [id]` — same flags as create
- `trib contacts delete [id]`
- `trib contacts bulk-delete` — with `--ids` (comma-separated)
- `trib contacts bulk-status` — with `--ids`, `--status`
- `trib contacts send-message [id]` — with `--body`, `--from`
- `trib contacts toggle-ai [id]` — with `--enable/--disable`
- `trib contacts qualify [id]`
- `trib contacts timeline [id]`
- `trib contacts import` — with `--file` (CSV path)

### Task 6: Tags + Segments

`internal/content/tags.go`:
- `trib tags list`, `trib tags create --name --color`, `trib tags get [id]`, `trib tags update [id]`, `trib tags delete [id]`
- `trib tags bulk --action add/remove --tag-id --contact-ids`

`internal/content/segments.go`:
- `trib segments list`, `trib segments create --name --definition` (JSON), `trib segments get [id]`, `trib segments update [id]`, `trib segments delete [id]`
- `trib segments resolve [id]` — get contact IDs
- `trib segments refresh [id]`

### Task 7: Conversations

`internal/conversations/conversations.go`:
- `trib conversations list` — `--status`, `--channel`, `--unread`
- `trib conversations get [id]` — includes messages
- `trib conversations send [id]` — `--body`
- `trib conversations ai-toggle [id]` — `--enable/--disable`
- `trib conversations ai-pause [id]`
- `trib conversations ai-resume [id]`
- `trib conversations assign [id]` — `--agent-id`
- `trib conversations clear [id]` — delete messages
- `trib conversations followup-status [id]`
- `trib conversations followup-settings [id]` — `--enabled`, `--delay`, etc.
- `trib conversations followup-generate [id]`
- `trib conversations followup-send [id]`
- `trib conversations followup-reset [id]`

### Task 8: Agents + Prompt Versions + Suggestions

`internal/agents/agents.go`:
- `trib agents list`, `trib agents create`, `trib agents get [id]`, `trib agents update [id]`, `trib agents delete [id]`
- Create/update flags: `--name`, `--prompt`, `--greeting`, `--voice-id`, `--language`, `--channel` (text/voice/both)
- `trib agents embed [id]` — get embed settings + code
- `trib agents embed-update [id]` — `--domains`, `--enabled`

Prompt versions (subcommands under agents):
- `trib agents prompts list [agent-id]`
- `trib agents prompts active [agent-id]`
- `trib agents prompts create [agent-id]`
- `trib agents prompts get [agent-id] [version-id]`
- `trib agents prompts activate [agent-id] [version-id]`
- `trib agents prompts rollback [agent-id] [version-id]`
- `trib agents prompts stats [agent-id] [version-id]`
- `trib agents prompts compare [agent-id]` — `--v1`, `--v2`
- `trib agents prompts winner [agent-id]`
- `trib agents prompts test [agent-id] [version-id]` — activate for testing
- `trib agents prompts deactivate [agent-id] [version-id]`
- `trib agents prompts pause [agent-id] [version-id]`
- `trib agents prompts resume [agent-id] [version-id]`
- `trib agents prompts eliminate [agent-id] [version-id]`

Suggestions:
- `trib agents suggestions list` — `--agent-id`, `--status`
- `trib agents suggestions pending-count`
- `trib agents suggestions stats`
- `trib agents suggestions get [id]`
- `trib agents suggestions approve [id]`
- `trib agents suggestions reject [id]` — `--reason`
- `trib agents suggestions generate [agent-id]`

### Task 9: SMS Campaigns

`internal/campaigns/sms.go`:
- `trib campaigns list` — `--status`
- `trib campaigns create` — `--name`, `--agent-id`, `--message`, `--rate`, etc.
- `trib campaigns get [id]`
- `trib campaigns update [id]`
- `trib campaigns delete [id]`
- `trib campaigns start [id]`
- `trib campaigns pause [id]`
- `trib campaigns resume [id]`
- `trib campaigns cancel [id]`
- `trib campaigns duplicate [id]`
- `trib campaigns add-contacts [id]` — `--contact-ids`
- `trib campaigns list-contacts [id]`
- `trib campaigns analytics [id]`
- `trib campaigns guarantee [id]`

### Task 10: Voice Campaigns

`internal/campaigns/voice.go`:
- `trib voice-campaigns list/create/get/update`
- `trib voice-campaigns start/pause/resume/cancel [id]`
- `trib voice-campaigns add-contacts/list-contacts [id]`
- `trib voice-campaigns analytics/guarantee [id]`

### Task 11: Campaign Reports

`internal/campaigns/reports.go`:
- `trib campaign-reports list`
- `trib campaign-reports count`
- `trib campaign-reports get [id]`
- `trib campaign-reports for-campaign [campaign-id]`
- `trib campaign-reports generate` — `--campaign-id`

### Task 12: Calls + Outcomes + Feedback

`internal/calls/calls.go`:
- `trib calls list` — `--direction`, `--status`, `--search`
- `trib calls get [id]` — includes recording, transcript
- `trib calls dial` — `--to`, `--from`, `--agent-id`
- `trib calls hangup [id]`
- `trib calls outcome [message-id]` — get outcome
- `trib calls outcome-update [message-id]` — `--type`, manual override
- `trib calls feedback [message-id]` — `--rating`, `--thumbs`, `--text`, `--quality-score`
- `trib calls feedback-list [message-id]`
- `trib calls feedback-summary [message-id]`

### Task 13: Appointments

`internal/appointments/appointments.go`:
- `trib appointments list` — `--status`, `--contact-id`, `--agent-id`, `--from`, `--to`
- `trib appointments stats` — `--agent-id`, `--campaign-id`
- `trib appointments create` — `--contact-id`, `--agent-id`, `--scheduled-at`, `--duration`
- `trib appointments get [id]`
- `trib appointments update [id]`
- `trib appointments delete [id]`
- `trib appointments sync [id]` — retry Cal.com sync
- `trib appointments remind [id]` — send SMS reminder

### Task 14: Opportunities & Pipelines

`internal/pipeline/pipeline.go`:
- `trib pipelines list/create/get/update/delete`
- `trib pipelines add-stage [pipeline-id]` — `--name`, `--order`, `--probability`, `--type`
- `trib pipelines update-stage [pipeline-id] [stage-id]`
- `trib opportunities list` — `--pipeline-id`, `--stage-id`, `--search`
- `trib opportunities create/get/update/delete`
- `trib opportunities add-item [id]` — `--name`, `--quantity`, `--unit-price`
- `trib opportunities update-item [id] [item-id]`
- `trib opportunities delete-item [id] [item-id]`

### Task 15: Offers + Lead Magnets

`internal/offers/offers.go`:
- `trib offers list/create/get/update/delete`
- `trib offers generate` — AI generate offer content
- `trib offers with-magnets [id]`
- `trib offers attach-magnet [id]` — `--magnet-id`
- `trib offers detach-magnet [id] [magnet-id]`
- `trib offers reorder-magnets [id]` — `--order` (JSON)
- `trib lead-magnets list/create/get/update/delete`
- `trib lead-magnets generate-quiz` — AI generate quiz
- `trib lead-magnets generate-calculator` — AI generate calculator
- `trib lead-magnets increment-download [id]`

### Task 16: Phone Numbers

`internal/phone/phone.go`:
- `trib phone list`
- `trib phone get [id]`
- `trib phone update [id]`
- `trib phone search` — `--country`, `--area-code`, `--contains`
- `trib phone purchase` — `--phone-number`
- `trib phone release [id]`
- `trib phone sync` — sync from Telnyx

### Task 17: Message Templates + Message Tests

`internal/content/templates.go`:
- `trib templates list/create/get/update/delete`

`internal/content/tests.go`:
- `trib message-tests list/create/get/update/delete`
- `trib message-tests variants [id]` — list variants
- `trib message-tests add-variant [id]` — `--name`, `--message`
- `trib message-tests update-variant [id] [variant-id]`
- `trib message-tests delete-variant [id] [variant-id]`
- `trib message-tests add-contacts [id]` — `--contact-ids`
- `trib message-tests list-contacts [id]`
- `trib message-tests start/pause/complete [id]`
- `trib message-tests analytics [id]`
- `trib message-tests select-winner [id]` — `--variant-id`
- `trib message-tests convert [id]` — convert to campaign

### Task 18: Admin — Integrations + Automations

`internal/admin/integrations.go`:
- `trib integrations list`
- `trib integrations get [type]` — type: calcom, telnyx, sendgrid, openai
- `trib integrations create` — `--type`, `--credentials` (JSON)
- `trib integrations update [type]`
- `trib integrations delete [type]`
- `trib integrations test [type]`

`internal/admin/automations.go`:
- `trib automations list/create/get/update/delete`
- `trib automations toggle [id]`
- `trib automations stats`

### Task 19: Admin — Workspaces + Lead Sources + Scraping + Invitations

`internal/admin/workspaces.go`:
- `trib workspaces list/create/get/update/delete`
- `trib workspaces members [id]` — list members
- `trib workspaces add-member [id]` — `--email`, `--role`
- `trib workspaces remove-member [id] [user-id]`

`internal/admin/lead_sources.go`:
- `trib lead-sources list/create/get/update/delete`

`internal/admin/scraping.go`:
- `trib scraping search` — `--query`, `--location`
- `trib scraping import` — `--businesses` (JSON)
- `trib find-leads search` — same as scraping with AI enrichment
- `trib find-leads import`

`internal/admin/invitations.go`:
- `trib invitations list`
- `trib invitations send` — `--email`, `--role`
- `trib invitations revoke [id]`

### Task 20: Commands Index + Final Polish

- Complete `trib commands` with every single command registered
- Ensure `trib setup` tests connection and shows API key config guide
- `trib setup show` — detailed setup instructions
- Add `CLAUDE.md` with build/test/lint instructions
- Run `go build`, `go vet`, fix all issues

## Implementation Notes

### Config Keys (flat JSON, `~/.config/trib/config.json`)
```json
{
  "api_key": "trib_xxxxxxxxxxxx",
  "api_url": "https://api.yourdomain.com",
  "workspace_id": "uuid-here"
}
```

### Command Pattern (follow pocket exactly)
Every leaf command:
1. Read config (`config.MustGet("api_key")`)
2. Build URL via `api.WorkspaceURL("/contacts?page=1")`
3. Call `api.Get(url, &result)`
4. Transform to LLM-friendly struct
5. `output.Print(result)`

### Error Pattern
```go
return output.PrintError("fetch_failed", err.Error(), nil)
```

### LLM-Friendly Output
- Flatten nested objects
- Truncate long strings (descriptions, prompts → 120 chars)
- Convert timestamps to relative ages ("3h ago")
- Short field names (`desc` not `description`)

## Risks
1. **Backend API key auth** is new — must be rock-solid since it's the auth backbone for all CLI ops
2. **200+ commands** is a lot — but each follows the same pattern, so it's mechanical once the scaffold is right
3. **go 1.25.6** in pocket's go.mod — we need to match whatever Go version is installed

## Verification
After each task:
- `cd /home/groot/trib-cli && go build ./...` must pass
- `go vet ./...` must pass
- For backend: `cd /home/groot/aicrm/backend && uv run ruff check app && uv run mypy app`
- Test the actual commands against a running backend where feasible
