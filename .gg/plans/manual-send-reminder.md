# Plan: Manual Send-Reminder Endpoint + Calendar UI Button

## Overview
Allow staff to manually trigger a reminder SMS for any scheduled appointment directly from the calendar UI. Full stack: backend service extraction → new POST endpoint → frontend API client → hook → calendar dialog button + contact sidebar button with loading/success/error states.

---

## Files to Create
- `backend/app/services/calendar/reminder_service.py` — shared reminder logic

## Files to Modify
- `backend/app/workers/reminder_worker.py` — refactor to use reminder_service
- `backend/app/api/v1/appointments.py` — new POST `/{appointment_id}/send-reminder` endpoint
- `backend/app/schemas/appointment.py` — add `SendReminderResponse` schema
- `frontend/src/lib/api/appointments.ts` — add `sendReminder()` + response type
- `frontend/src/hooks/useAppointments.ts` — add `useSendAppointmentReminder` hook
- `frontend/src/components/calendar/calendar-page.tsx` — add button in dialog
- `frontend/src/components/contacts/contact-sidebar.tsx` — add button to scheduled appointments

---

## Step 1: Create `backend/app/services/calendar/reminder_service.py`

Extract shared logic from `ReminderWorker` into standalone async functions:

### Functions to create:

```python
async def resolve_from_number(
    db: AsyncSession,
    contact_id: int,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID | None,
) -> str | None:
    """Strategy 1: existing conversation, 2: agent phone, 3: any workspace SMS number."""
    # Copy logic from ReminderWorker._resolve_from_number verbatim

def render_reminder_body(
    template: str | None,
    contact: Contact,
    appointment: Appointment,
    workspace: Workspace,
    agent: Agent | None,
) -> str:
    """Build SMS body from template or default. Copy from ReminderWorker._render_reminder_body."""
    # Copy logic verbatim (non-async — no I/O)

async def send_appointment_reminder(
    db: AsyncSession,
    appointment: Appointment,
    contact: Contact,
    workspace: Workspace,
) -> dict[str, str | bool]:
    """
    Send a manual reminder SMS for an appointment.
    Returns: {"success": bool, "message": str, "sent_to": str}
    
    Does NOT mark offsets as sent (this is a manual send, not a scheduled one).
    DOES update reminder_sent_at on the appointment.
    Respects opt-out (raises ValueError with descriptive message).
    """
```

**Key logic for `send_appointment_reminder`:**
1. Check `settings.telnyx_api_key` — raise `ValueError("No Telnyx API key configured")` if missing
2. Check `contact.phone_number` — raise `ValueError("Contact has no phone number on file")`
3. Check opt-out via `OptOutManager().check_opt_out(workspace.id, contact_phone, db)` — raise `ValueError("Contact has opted out of SMS")`
4. Call `resolve_from_number(db, contact.id, workspace.id, agent_id)` — raise `ValueError("No SMS-enabled phone number available for this workspace")` if None
5. Render body with `render_reminder_body(agent.reminder_template if agent else None, contact, appointment, workspace, agent)`
6. Call `TelnyxSMSService(telnyx_key).send_message(...)` 
7. Update `appointment.reminder_sent_at = datetime.now(UTC)` and `await db.commit()`
8. Return `{"success": True, "message": "Reminder sent", "sent_to": mask_phone(contact_phone)}`

**Helper: `mask_phone(phone: str) -> str`**
- Returns last 4 digits masked as `***-***-1234`

---

## Step 2: Refactor `backend/app/workers/reminder_worker.py`

Replace the worker's `_resolve_from_number` and `_render_reminder_body` implementations with calls to `reminder_service`:

```python
from app.services.calendar.reminder_service import resolve_from_number, render_reminder_body

# In _send_reminder():
from_number = await resolve_from_number(db, contact.id, workspace.id, agent_id)
body = render_reminder_body(agent.reminder_template if agent else None, contact, appt, workspace, agent)
```

Keep `_mark_offset_sent` in the worker (it's worker-specific, tracks which scheduled offsets fired).
Keep `_send_reminder` in the worker — it still orchestrates the full flow including marking offsets and conversation assignment.

---

## Step 3: Add `SendReminderResponse` schema to `backend/app/schemas/appointment.py`

```python
class SendReminderResponse(BaseModel):
    """Response for manual reminder send."""
    success: bool
    message: str
    sent_to: str  # masked phone number, e.g. "***-***-1234"
```

---

## Step 4: Add endpoint to `backend/app/api/v1/appointments.py`

```python
@router.post("/{appointment_id}/send-reminder", response_model=SendReminderResponse)
async def send_appointment_reminder_endpoint(
    workspace_id: uuid.UUID,
    appointment_id: int,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> SendReminderResponse:
    """Manually send a reminder SMS for a scheduled appointment."""
```

**Logic:**
1. Query appointment with `selectinload(Appointment.contact)` + `selectinload(Appointment.agent)` where `id == appointment_id AND workspace_id == workspace_id`
2. If not found → 404
3. If `appointment.status != "scheduled"` → 400 `"Only scheduled appointments can receive reminders"`
4. If `appointment.contact is None` → 400 `"Appointment has no associated contact"`
5. Try `result = await send_appointment_reminder(db, appointment, appointment.contact, workspace)` from reminder_service
6. Catch `ValueError as e` → raise HTTPException 400 with `str(e)`
7. Return `SendReminderResponse(**result)`

**Imports to add:**
```python
from app.schemas.appointment import SendReminderResponse
from app.services.calendar.reminder_service import send_appointment_reminder
```

---

## Step 5: Add `sendReminder` to `frontend/src/lib/api/appointments.ts`

Add after the existing `appointmentsApi`:

```typescript
export interface SendReminderResponse {
  success: boolean;
  message: string;
  sent_to: string;  // masked phone, e.g. "***-***-1234"
}

export const appointmentsApi = {
  ...baseApi,
  sendReminder: async (workspaceId: string, appointmentId: number): Promise<SendReminderResponse> => {
    const path = `/api/v1/workspaces/${workspaceId}/appointments/${appointmentId}/send-reminder`;
    const response = await api.post(path);
    return response.data as SendReminderResponse;
  },
};
```

Need to import `api` from `@/lib/api` (already used by `createApiClient` internally, but not directly imported here). Check and add import.

---

## Step 6: Add `useSendAppointmentReminder` to `frontend/src/hooks/useAppointments.ts`

```typescript
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { appointmentsApi } from "@/lib/api/appointments";
import { appointmentQueryKeys } from "./useAppointments"; // already exported

export function useSendAppointmentReminder(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (appointmentId: number) =>
      appointmentsApi.sendReminder(workspaceId, appointmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["appointments", workspaceId] });
    },
  });
}
```

Export it from the same file.

---

## Step 7: Update `frontend/src/components/calendar/calendar-page.tsx`

**Imports to add:**
- `Bell, CheckCircle2` from `lucide-react`
- `useSendAppointmentReminder` from `@/hooks/useAppointments`
- `formatDistanceToNow` from `date-fns`

**New state/mutation at top of `CalendarPage`:**
```typescript
const sendReminderMutation = useSendAppointmentReminder(workspaceId ?? "");
const [reminderSentForId, setReminderSentForId] = useState<number | null>(null);
```

**New handler:**
```typescript
const handleSendReminder = async (appointmentId: number) => {
  sendReminderMutation.mutate(appointmentId, {
    onSuccess: (data) => {
      setReminderSentForId(appointmentId);
      toast.success(`Reminder sent to ${data.sent_to}`);
      // Reset checkmark after 3 seconds
      setTimeout(() => setReminderSentForId(null), 3000);
    },
    onError: (error: unknown) => {
      const msg = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to send reminder";
      toast.error(msg);
    },
  });
};
```

**In the DialogContent (after the contact info row, before the grid gap-2 div):**
```tsx
{apt.status === "scheduled" && (
  <div className="flex items-center gap-2">
    <Button
      variant="outline"
      size="sm"
      onClick={() => handleSendReminder(apt.id)}
      disabled={sendReminderMutation.isPending}
      className={reminderSentForId === apt.id ? "text-green-600 border-green-300" : ""}
    >
      {sendReminderMutation.isPending && sendReminderMutation.variables === apt.id ? (
        <><Loader2 className="mr-2 size-4 animate-spin" />Sending...</>
      ) : reminderSentForId === apt.id ? (
        <><CheckCircle2 className="mr-2 size-4" />Reminder Sent</>
      ) : (
        <><Bell className="mr-2 size-4" />Send Reminder</>
      )}
    </Button>
    {apt.reminder_sent_at && (
      <span className="text-xs text-muted-foreground">
        Last sent {formatDistanceToNow(new Date(apt.reminder_sent_at), { addSuffix: true })}
      </span>
    )}
  </div>
)}
```

---

## Step 8: Update `frontend/src/components/contacts/contact-sidebar.tsx`

**Import additions:**
- `Bell` from `lucide-react` (may already be imported)
- `useSendAppointmentReminder` from `@/hooks/useAppointments`
- `useWorkspaceId` from `@/hooks/use-workspace-id`

**Add mutation in component:**
```typescript
const workspaceId = useWorkspaceId();
const sendReminderMutation = useSendAppointmentReminder(workspaceId ?? "");
```

**Update the appointment item in the sidebar** (inside `contactAppointments.map`) to add a send-reminder button for `apt.status === 'scheduled'`:

```tsx
{apt.status === "scheduled" && (
  <Button
    variant="ghost"
    size="icon"
    className="h-6 w-6 text-muted-foreground hover:text-foreground"
    onClick={(e) => {
      e.stopPropagation();
      sendReminderMutation.mutate(apt.id, {
        onSuccess: (data) => toast.success(`Reminder sent to ${data.sent_to}`),
        onError: (error: unknown) => {
          const msg = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to send reminder";
          toast.error(msg);
        },
      });
    }}
    disabled={sendReminderMutation.isPending && sendReminderMutation.variables === apt.id}
    title="Send reminder SMS"
  >
    {sendReminderMutation.isPending && sendReminderMutation.variables === apt.id ? (
      <Loader2 className="h-3 w-3 animate-spin" />
    ) : (
      <Bell className="h-3 w-3" />
    )}
  </Button>
)}
```

---

## Verification Steps

1. **Backend**: `cd backend && uv run ruff check app && uv run mypy app`
2. **Frontend**: `cd frontend && npm run lint && npm run build`
3. **Logical checks**:
   - `reminder_worker.py` still calls `_send_reminder()` which now delegates `resolve_from_number` and `render_reminder_body` to the service
   - Worker `_mark_offset_sent` remains in worker (specific to scheduled reminders, not manual)
   - Manual endpoint does NOT mark offsets — it only updates `reminder_sent_at`
   - Error cases covered: no phone, opted out, no from number, wrong status, not found

## Commit
```
feat: manual send-reminder endpoint and calendar UI button with loading/success/error states
```
