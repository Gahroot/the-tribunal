# The Tribunal - AI CRM

AI-powered CRM platform that manages leads through calls, SMS, and messages with AI voice agents and SMS campaigns, featuring a Next.js dashboard with Cal.com appointment booking integration.

## Project Structure

```
frontend/                           # Next.js 16 React frontend
  ├── src/
  │   ├── app/                      # App Router pages (agents, campaigns, contacts, etc.)
  │   ├── components/               # React components
  │   │   ├── ui/                   # Base UI components (Radix/shadcn)
  │   │   ├── agents/               # AI agents components
  │   │   ├── campaigns/            # Campaign management
  │   │   ├── contacts/             # Contact components
  │   │   ├── layout/               # Layout components
  │   │   └── ...
  │   ├── lib/                      # Utilities and services
  │   │   ├── api/                  # API client functions
  │   │   └── services/             # Service implementations
  │   ├── hooks/                    # Custom React hooks
  │   └── types/                    # TypeScript types
  └── package.json

backend/                            # FastAPI Python backend
  ├── app/
  │   ├── api/v1/                   # API v1 endpoints
  │   ├── models/                   # SQLAlchemy ORM models
  │   ├── schemas/                  # Pydantic schemas
  │   ├── services/                 # Business logic (ai, telephony, calendar)
  │   ├── core/                     # Config and security
  │   ├── db/                       # Database utilities
  │   ├── workers/                  # Background job workers
  │   └── websockets/               # WebSocket handlers
  ├── alembic/versions/             # Database migrations
  └── pyproject.toml
```

## Tech Stack

**Frontend:** Next.js 16, React 19, TypeScript, TailwindCSS 4, shadcn/ui, React Query, Zustand
**Backend:** FastAPI, Python 3.12+, SQLAlchemy 2, PostgreSQL, Redis, Alembic
**Integrations:** OpenAI Realtime API, Telnyx (VoIP/SMS), Cal.com

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
- Services → `app/services/`, grouped by domain (ai, telephony, calendar)
- Migrations → `alembic/versions/`

## Code Quality - Zero Tolerance

After editing ANY frontend file, run:
```bash
cd frontend && npm run lint && npm run build
```

After editing ANY backend file, run:
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
