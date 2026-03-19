# Plan: Multi-Touch Reminders Schema

## Overview

Add three new database columns for multi-touch appointment reminders:
1. `agents.reminder_offsets` — `INTEGER[]` list of minutes-before offsets (default `{1440,120,30}`)
2. `agents.reminder_template` — `TEXT` nullable custom SMS body
3. `appointments.reminders_sent` — `INTEGER[]` tracks which offsets have already fired (default `{}`)

**Keep `reminder_minutes_before`** — it's referenced in too many places to safely remove in this task:
- `backend/app/api/v1/agents.py` (AgentCreate, AgentUpdate, AgentResponse, create_agent handler line 205)
- `backend/app/workers/reminder_worker.py` (lines 50, 94)
- `frontend/src/lib/api/agents.ts` (lines 31, 74, 102)
- `frontend/src/app/agents/[id]/page.tsx` (lines 156, 249)
- `frontend/src/components/agents/create-agent-form.tsx` (line 274)

---

## Current State

- Migration chain head: `d2e3f4g5h6i7` (`d2e3f4g5h6i7_create_lead_sources_table.py`)
- Agent model: `backend/app/models/agent.py` — already imports `ARRAY` from `sqlalchemy.dialects.postgresql`
- Agent schemas: **inline in `backend/app/api/v1/agents.py`** (no separate `schemas/agent.py`)
- Appointment schemas: `backend/app/schemas/appointment.py`
- Frontend Agent type (API): `frontend/src/lib/api/agents.ts` — `AgentResponse`, `CreateAgentRequest`, `UpdateAgentRequest`
- Frontend Appointment type: `frontend/src/types/index.ts` — `Appointment` interface (line 225)

---

## Implementation Steps

### 1. Backend Model — `backend/app/models/agent.py`

Add after `reminder_minutes_before` (line 107):

```python
# Appointment reminder settings — multi-touch offsets
reminder_offsets: Mapped[list[int]] = mapped_column(
    ARRAY(Integer), default=lambda: [1440, 120, 30], nullable=False
)
reminder_template: Mapped[str | None] = mapped_column(Text, nullable=True)
```

`Integer` is already imported. `Text` is already imported. `ARRAY` is already imported.

### 2. Backend Model — `backend/app/models/appointment.py`

Add after `reminder_sent_at` (line 90):

```python
# Multi-touch reminder tracking — list of offsets (minutes) already sent
reminders_sent: Mapped[list[int]] = mapped_column(
    ARRAY(Integer), default=list, nullable=False
)
```

Must add imports: `ARRAY` from `sqlalchemy.dialects.postgresql`, `Integer` from `sqlalchemy`.
Both `Integer` and `ARRAY` need to be added to the imports in appointment.py.

### 3. Alembic Migration

New file: `backend/alembic/versions/e3f4g5h6i7j8_add_multi_touch_reminder_fields.py`

- Revision ID: `e3f4g5h6i7j8`
- down_revision: `d2e3f4g5h6i7`
- Pattern: follows same import style as `d2e3f4g5h6i7_create_lead_sources_table.py`

```python
"""Add multi-touch reminder fields.

Revision ID: e3f4g5h6i7j8
Revises: d2e3f4g5h6i7
Create Date: 2026-03-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3f4g5h6i7j8"
down_revision: str | None = "d2e3f4g5h6i7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "reminder_offsets",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{1440,120,30}'"),
        ),
    )
    op.add_column(
        "agents",
        sa.Column("reminder_template", sa.Text(), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "reminders_sent",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("appointments", "reminders_sent")
    op.drop_column("agents", "reminder_template")
    op.drop_column("agents", "reminder_offsets")
```

### 4. Agent API Schemas — `backend/app/api/v1/agents.py`

**AgentCreate** — add after `reminder_minutes_before: int = 30`:
```python
reminder_offsets: list[int] = [1440, 120, 30]
reminder_template: str | None = None
```

**AgentUpdate** — add after `reminder_minutes_before: int | None = None`:
```python
reminder_offsets: list[int] | None = None
reminder_template: str | None = None
```

**AgentResponse** — add after `reminder_minutes_before: int`:
```python
reminder_offsets: list[int]
reminder_template: str | None
```

**create_agent handler** (line ~182, inside `Agent(...)` constructor) — add:
```python
reminder_offsets=agent_in.reminder_offsets,
reminder_template=agent_in.reminder_template,
```

The update_agent handler uses `model_dump(exclude_unset=True)` + `setattr` loop, so no explicit change needed for update.

### 5. Appointment Schema — `backend/app/schemas/appointment.py`

Add to `AppointmentResponse` after `reminder_sent_at`:
```python
reminders_sent: list[int] = []
```

### 6. Frontend — `frontend/src/lib/api/agents.ts`

Add to `AgentResponse` after `reminder_minutes_before: number`:
```typescript
reminder_offsets: number[];
reminder_template: string | null;
```

Add to `CreateAgentRequest` after `reminder_minutes_before?: number`:
```typescript
reminder_offsets?: number[];
reminder_template?: string | null;
```

Add to `UpdateAgentRequest` after `reminder_minutes_before?: number`:
```typescript
reminder_offsets?: number[];
reminder_template?: string | null;
```

### 7. Frontend — `frontend/src/types/index.ts`

Add to `Appointment` interface (after `reminder_sent_at?: string`):
```typescript
reminders_sent?: number[];
```

---

## Verification

1. `cd backend && uv run alembic upgrade head` — apply migration
2. `cd backend && uv run ruff check app` — lint
3. `cd backend && uv run mypy app` — type check
4. `cd frontend && npm run lint && npm run build` — frontend check
5. `grep -r "reminder_minutes_before" backend/ frontend/` — confirm no broken refs

---

## Risk Notes

- **Safe defaults**: All new columns have `server_default` so existing rows are populated automatically
- **Worker not changed**: The existing `reminder_minutes_before` logic in the worker continues unchanged
- **No data loss**: `reminder_minutes_before` column is kept; existing code continues working
- **Migration is additive only** — no drops, no rewrites of existing columns
