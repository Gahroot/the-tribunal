# The Tribunal - AI CRM

AI-powered CRM platform that manages leads through calls, SMS, and messages with AI voice agents and SMS campaigns, featuring a Next.js dashboard with Cal.com appointment booking integration and human-in-the-loop approval gates.

## Project Structure

```
frontend/                           # Next.js 16 React frontend
  src/
    app/                            # App Router pages (27 route groups)
      agents/, campaigns/, contacts/, calls/, dashboard/, settings/
      offers/, experiments/, suggestions/, lead-magnets/, opportunities/
      automations/, calendar/, find-leads/, phone-numbers/, voice-test/
      pending-actions/, billing/, nudges/, onboarding/
    components/                     # React components (one per file, 29 feature groups)
      ui/                           # shadcn/ui primitives (Radix-based)
      agents/, campaigns/, contacts/, calls/, conversation/, settings/
      opportunities/, automations/, calcom/, layout/, auth/, wizard/
      pending-actions/, nudges/, suggestions/, tags/, segments/
    lib/
      api/                          # API client functions (one per resource)
      api.ts                        # Axios fetch wrapper
      utils/                        # Utility functions
      contact-store.ts              # Zustand store
    hooks/                          # Custom React hooks (useContacts, useWizard, etc.)
    providers/                      # Auth, workspace, combined providers
    types/                          # TypeScript type definitions
    widget/                         # Embeddable chat widget

backend/                            # FastAPI Python backend
  app/
    main.py                         # FastAPI app entrypoint
    api/v1/                         # Versioned API routes (43 resource modules)
    api/webhooks/                   # Incoming webhook handlers (Telnyx, Cal.com)
    models/                         # SQLAlchemy ORM models (43 files)
    schemas/                        # Pydantic schemas (39 files)
    services/                       # Business logic by domain (24 service groups)
      ai/, telephony/, calendar/, campaigns/, contacts/
      conversations/, opportunities/, segments/, tags/, tools/
      approval/, knowledge/, nudges/, appointments/
    core/                           # Config, security, logging, encryption
    db/                             # Session factory, Redis, pagination
    utils/                          # Calendar, phone, datetime helpers
    workers/                        # Background jobs (17 worker types)
    websockets/                     # Voice bridge, real-time handlers
  alembic/versions/                 # Database migrations
  tests/                            # Pytest test suite (api/, schemas/, services/, workers/)
```

## Tech Stack

**Frontend:** Next.js 16, React 19, TypeScript 5 (strict), TailwindCSS 4, shadcn/ui, React Query 5, Zustand 5, Zod 4, Framer Motion, Three.js/R3F
**Backend:** FastAPI, Python 3.12+, SQLAlchemy 2 (async), PostgreSQL 17, Redis 7, Alembic, uv
**Integrations:** OpenAI Realtime API, Telnyx (VoIP/SMS), Cal.com, ElevenLabs, SendGrid

## Organization Rules

**Frontend:**
- Pages → `src/app/` (Next.js App Router)
- Components → `src/components/`, one per file, grouped by feature
- API clients → `src/lib/api/`, one file per resource
- Utilities → `src/lib/utils/`, grouped by functionality
- Types → `src/types/` or co-located

**Backend:**
- API routes → `app/api/v1/`, one file per resource
- Models → `app/models/`, one model per file
- Schemas → `app/schemas/`, matching model structure
- Services → `app/services/`, grouped by domain (ai, telephony, calendar, approval, knowledge)
- Workers → `app/workers/`, one worker per job type
- Migrations → `alembic/versions/`

## Code Quality - Zero Tolerance

After editing ANY frontend file:
```bash
cd frontend && npm run lint && npm run build
```

After editing ANY backend file:
```bash
cd backend && uv run ruff check app && uv run mypy app
```

Fix ALL errors/warnings before continuing.

## Shared primitives

Prefer these canonical patterns over rolling new ones:

- `backend/app/services/contacts/contact_filters.py` — gold-standard filter engine. Reuse `apply_contact_filters()` and the `FilterDefinition` shape for any list endpoint that needs rule-based filtering.
- `frontend/src/lib/query-keys.ts` — canonical React Query key factory. All new hooks should pull keys from here rather than inlining tuples.
- `frontend/src/lib/query-options.ts` — shared query option presets (stale times, retry policies). Compose these instead of hand-tuning per-hook.
- `frontend/src/components/ui/page-state.tsx` — `PageLoadingState`, `PageErrorState`, `PageEmptyState`. Use for every page-level loading/error/empty surface so the app renders consistent states.

## Development

```bash
cd backend && docker compose up -d                              # PostgreSQL + Redis
cd frontend && npm run dev                                      # Frontend :3000
cd backend && uv run uvicorn app.main:app --reload --port 8000  # Backend :8000
cd backend && uv run alembic upgrade head                       # Migrations
cd backend && uv run pytest                                     # Tests
```

## Production

The app is deployed on Railway. Use `railway` CLI for logs, deploys, and environment management.
This is a live, actively used CRM with real contact data. Never run destructive database operations (DROP, TRUNCATE, DELETE without WHERE) against production. Always test migrations locally first and back up data before schema changes that touch contact/lead tables.
