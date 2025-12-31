# The Tribunal

This is where the decisions happen.

Every lead that comes through your door ends up here. Every conversation, every follow-up, every "let me think about it" — it all flows through The Tribunal. This is your business's command center, the place where prospects become customers and deals get closed.

## What Happens Here

**Leads arrive.** They come in through calls, messages, campaigns. The Tribunal captures them all.

**AI takes the first swing.** Voice agents handle incoming calls. SMS campaigns run on autopilot. Your AI doesn't sleep, doesn't take breaks, doesn't forget to follow up.

**You make the call.** When it's time for a human touch, you step in. Review conversations, check the history, and close the deal. The Tribunal gives you everything you need to make the right decision at the right moment.

**Appointments get booked.** Cal.com integration means leads can book time with you directly. No back-and-forth. No missed opportunities.

## The Setup

This is a monorepo with two parts:

```
the-tribunal/
├── frontend/    → Next.js dashboard (where you command)
├── backend/     → FastAPI API (where the magic happens)
```

### Fire Up the Backend

```bash
cd backend
uv sync
docker compose up -d
cp .env.example .env   # configure your secrets
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

API docs at http://localhost:8000/docs

### Launch the Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at http://localhost:3000

## The Arsenal

**Frontend**: Next.js 16, React 19, TailwindCSS, React Query, Zustand

**Backend**: FastAPI, SQLAlchemy (async), PostgreSQL, Redis, OpenAI Realtime, Telnyx

## The Bottom Line

Your leads deserve better than spreadsheets and sticky notes. The Tribunal is where you take control — where every interaction is tracked, every opportunity is surfaced, and every decision is informed.

Welcome to the command center. Time to close some deals.
