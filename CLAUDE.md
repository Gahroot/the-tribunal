# The Tribunal - AI CRM

AI-powered CRM platform that manages leads through calls, SMS, and messages with AI voice agents and SMS campaigns, featuring a Next.js dashboard with Cal.com appointment booking integration.

## Project Structure

```
frontend/                           # Next.js 16 React frontend
  src/
    app/                            # App Router pages
      agents/, campaigns/, contacts/, calls/, dashboard/, settings/
    components/                     # React components by feature
      ui/                           # Base UI (Radix/shadcn)
      agents/, campaigns/, contacts/, calls/, conversation/, settings/
    lib/
      api/                          # API client functions (one per resource)
      services/                     # Service implementations
    hooks/                          # Custom React hooks
    types/                          # TypeScript types

backend/                            # FastAPI Python backend
  app/
    api/v1/                         # API endpoints (one per resource)
    models/                         # SQLAlchemy ORM models
    schemas/                        # Pydantic schemas
    services/                       # Business logic
      ai/                           # Voice agents, IVR, qualification
        grok/                       # Grok session, DTMF, audio
        testing/                    # IVR test harness
      telephony/                    # Telnyx VoIP/SMS
      calendar/                     # Cal.com integration
      campaigns/                    # Campaign services
    core/                           # Config, security, logging
    db/                             # Database utilities
    workers/                        # Background jobs (campaign, enrichment, followup)
    websockets/                     # Voice bridge, real-time handlers
  alembic/versions/                 # Database migrations
  tests/                            # Pytest test suite
```

## Tech Stack

**Frontend:** Next.js 16, React 19, TypeScript, TailwindCSS 4, shadcn/ui, React Query, Zustand
**Backend:** FastAPI, Python 3.12+, SQLAlchemy 2, PostgreSQL 17, Redis 7, Alembic
**Integrations:** OpenAI Realtime API, Telnyx (VoIP/SMS), Cal.com, ElevenLabs

## Organization Rules

**Frontend:**
- Pages → `src/app/` (Next.js App Router)
- Components → `src/components/`, one per file, grouped by feature
- API clients → `src/lib/api/`, one file per resource
- Utilities → `src/lib/`, grouped by functionality
- Types → `src/types/` or co-located

**Backend:**
- API routes → `app/api/v1/`, one file per resource
- Models → `app/models/`, one model per file
- Schemas → `app/schemas/`, matching model structure
- Services → `app/services/`, grouped by domain (ai, telephony, calendar, campaigns)
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

## Development Servers

**Frontend:**
```bash
cd frontend && npm run dev
```

**Backend:**
```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

**Database migrations:**
```bash
cd backend && uv run alembic upgrade head
```

If changes require server restart, read server output and fix ALL warnings/errors.
