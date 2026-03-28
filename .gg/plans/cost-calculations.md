# Plan: Cost Calculations (Grok Voice + Telnyx)

## Overview
Add cost tracking and display for the two billing surfaces:
- **Voice agents** — Grok Realtime API + Telnyx telephony (per-minute)
- **SMS/texts** — Telnyx messaging (per-segment)

All data already exists in the `messages` table. No new migrations needed.

---

## Pricing Rates (from official sources)

### Grok Voice API (xAI)
- Realtime voice sessions: **$0.05 / min** ($3.00/hr)

### Telnyx Voice
- Media Streaming over WebSockets: **$0.0035 / min**
- Outbound/inbound call: **$0.002 / min**
- **Subtotal Telnyx voice per min: $0.0055**

### Total per voice minute (Grok + Telnyx): **$0.0555 / min**

### Telnyx SMS
- Outbound SMS (10DLC local): **$0.004 / segment**
- Inbound SMS: **$0.004 / segment**  
  (A segment = 160 chars GSM-7 or 70 chars UCS-2; estimate 1 segment per 160 chars)

---

## What Data We Have

From `messages` table:
- `channel`: `'voice'` or `'sms'`
- `direction`: `'outbound'` / `'inbound'`
- `duration_seconds`: voice call duration (nullable)
- `body`: SMS text (for segment estimation)
- `is_ai`: whether AI sent it
- `conversation_id` → `Conversation.workspace_id` for scoping

From `agents` table:
- `voice_provider`: `'grok'` / `'openai'` / `'elevenlabs'` (filter to grok)

---

## Files to Change

### Backend

#### 1. `backend/app/schemas/dashboard.py`
Add three new schemas before `DashboardResponse`, then add `cost_stats` field:

```python
class VoiceCostBreakdown(BaseModel):
    total_calls: int
    total_minutes: float
    grok_cost: float       # Grok Voice API portion
    telnyx_cost: float     # Telnyx telephony portion
    total_cost: float

class SmsCostBreakdown(BaseModel):
    total_messages: int
    total_segments: int
    telnyx_cost: float
    total_cost: float

class CostStats(BaseModel):
    period_label: str      # e.g. "March 2026"
    voice: VoiceCostBreakdown
    sms: SmsCostBreakdown
    grand_total: float
```

Add to `DashboardResponse`:
```python
cost_stats: CostStats
```

#### 2. `backend/app/services/dashboard/dashboard_service.py`
Add cost calculation constants at module level:
```python
# Cost rates
GROK_VOICE_PER_MIN = 0.05
TELNYX_VOICE_PER_MIN = 0.0055   # WebSocket $0.0035 + call $0.002
TOTAL_VOICE_PER_MIN = GROK_VOICE_PER_MIN + TELNYX_VOICE_PER_MIN  # $0.0555

TELNYX_SMS_PER_SEGMENT = 0.004
SMS_CHARS_PER_SEGMENT = 160
```

Add `get_cost_stats(workspace)` method that:
1. Calculates this-month date range
2. Queries voice messages (channel='voice') this month scoped to workspace, joins agent to filter `voice_provider='grok'`  
   — sums `duration_seconds`, counts calls
3. Queries outbound SMS messages this month, sums `len(body)` via Python (or `func.sum(func.length(Message.body))` in SQL)
4. Returns `CostStats` with breakdowns

Wire into `get_full_dashboard()` — call `get_cost_stats()`, include in `DashboardResponse`, update Redis cache serialization.

Import `CostStats`, `VoiceCostBreakdown`, `SmsCostBreakdown` from schemas.

#### 3. `backend/app/api/v1/dashboard.py` — no changes needed (already returns `DashboardResponse`)

---

### Frontend

#### 4. `frontend/src/lib/api/dashboard.ts`
Add interfaces:
```typescript
export interface VoiceCostBreakdown {
  total_calls: number;
  total_minutes: number;
  grok_cost: number;
  telnyx_cost: number;
  total_cost: number;
}

export interface SmsCostBreakdown {
  total_messages: number;
  total_segments: number;
  telnyx_cost: number;
  total_cost: number;
}

export interface CostStats {
  period_label: string;
  voice: VoiceCostBreakdown;
  sms: SmsCostBreakdown;
  grand_total: number;
}
```

Add `cost_stats: CostStats` to `DashboardResponse`.

#### 5. `frontend/src/components/dashboard/cost-breakdown-card.tsx` (new file)
New `CostBreakdownCard` component that receives `CostStats` and renders:
- Card header: "Cost Breakdown · {period_label}"  
- Two rows: **Voice (Grok + Telnyx)** and **SMS (Telnyx)**
  - Each shows: count (calls or messages), minutes/segments, and cost
  - Inline cost breakdown tooltip showing Grok vs Telnyx split for voice
- Footer: Total this month with a `DollarSign` icon

Use existing `Card`, `Badge`, `Tooltip` from shadcn/ui. Match dashboard card style.

#### 6. `frontend/src/components/dashboard/dashboard-page.tsx`
- Import `CostBreakdownCard` and `CostStats`
- Add a skeleton for cost card  
- Render `<CostBreakdownCard costStats={data?.cost_stats} isLoading={isLoading} />` in the bottom section of the dashboard (below agent stats, in its own row or alongside today's overview)

---

## Implementation Order

1. `backend/app/schemas/dashboard.py` — add schemas + field
2. `backend/app/services/dashboard/dashboard_service.py` — add constants + `get_cost_stats()` + wire into `get_full_dashboard()`
3. `frontend/src/lib/api/dashboard.ts` — add TS interfaces
4. `frontend/src/components/dashboard/cost-breakdown-card.tsx` — new component
5. `frontend/src/components/dashboard/dashboard-page.tsx` — integrate card

Then: `cd frontend && npm run lint && npm run build` and `cd backend && uv run ruff check app && uv run mypy app`

---

## Key Design Decisions

- **Scope**: Only voice calls where agent `voice_provider = 'grok'` count toward Grok Voice costs. All outbound SMS counts toward Telnyx SMS costs regardless of AI vs manual.
- **Period**: Current calendar month (month-to-date). Clear label like "March 2026".
- **Segments**: Estimate via `ceil(len(body) / 160)` — simple and accurate enough for standard English SMS.
- **No migration needed**: All data is in existing tables.
- **Cache**: Cost stats are included in the existing 5-min Redis cache for the dashboard.
- **Rounding**: Display to 2 decimal places (`$0.00`).

---

## Risks

- `duration_seconds` can be null (unanswered calls, failed calls) — handle with `COALESCE(duration_seconds, 0)` or Python `or 0`.
- Some outbound SMS are system messages (reminders, re-engagement) not AI conversations — these still incur Telnyx costs, so counting all outbound is correct.
- SIP trunking fees vary by destination — we use the base local rate ($0.002/min) as a conservative estimate.
