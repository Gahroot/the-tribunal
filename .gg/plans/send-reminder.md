# Plan: Manual Send-Reminder Feature

## Overview
Add a "Send Reminder" button to the calendar UI and contact sidebar that triggers a manual SMS reminder for any scheduled appointment, backed by a new POST endpoint.

---

## Backend

### 1. Create `backend/app/services/calendar/reminder_service.py`

Extract the SMS-sending logic from `ReminderWorker` into standalone async functions that can be shared between the worker and the new API endpoint.

**Functions to create:**
- `async def resolve_from_number(db, contact_id, workspace_id, agent_id) -> str | None`
  - Same 3-strategy logic as `ReminderWorker._resolve_from_number`
  - Strategy 1: existing conversation workspace_phone
  - Strategy 2: agent's assigned SMS-enabled phone
  - Strategy 3: any active SMS-enabled workspace phone
- `def render_reminder_body(template, contact, appointment, workspace, agent) -> str`
  - Same template rendering logic as `ReminderWorker._render_reminder_body`
- `async def send_appointment_reminder(db, appointment, workspace, contact, agent) -> dict`
  - Checks opt-out via `OptOutManager`
  - Calls `resolve_from_number`
  - Calls `render_reminder_body`
  - Calls `TelnyxSMSService.send_message()`
  - Updates `appointment.reminder_sent_at` and appends a sentinel (0 = manual) to `reminders_sent` array via raw SQL (same as `_mark_offset_sent`)
  - Returns `{"success": True, "message": "Reminder sent", "sent_to": masked_phone}`
  - Returns dict with `success: False` and error message for failures (opted out, no phone, no from number)
  - Raises on unexpected errors

**Masking helper:**
- `def mask_phone(phone: str) -> str` — returns `***-***-1234` style (last 4 digits)

### 2. Refactor `backend/app/workers/reminder_worker.py`
- Import the new functions from `reminder_service`
- Replace `_resolve_from_number` method: delegate to `resolve_from_number(...)`
- `_send_reminder` still stays in the worker but calls `resolve_from_number` + `render_reminder_body` from the service
- Do NOT remove the worker's `_mark_offset_sent` since offset tracking is worker-specific (the API endpoint uses offset=0 as "manual")

### 3. Add endpoint in `backend/app/api/v1/appointments.py`

```python
@router.post(
    "/{appointment_id}/send-reminder",
    response_model=dict,
    summary="Manually send an SMS reminder for a scheduled appointment",
)
async def send_appointment_reminder(
    workspace_id: uuid.UUID,
    appointment_id: int,
    current_user: CurrentUser,
    db: DB,
    workspace: Annotated[Workspace, Depends(get_workspace)],
) -> dict[str, Any]:
```

Steps:
1. Load appointment, validate it belongs to workspace (404 if not found)
2. Validate `appointment.status == "scheduled"` (400 if not)
3. Load contact via `appointment.contact_id`
4. Load agent via `appointment.agent_id` (may be None)
5. Import and call `reminder_service.send_appointment_reminder(db, appointment, workspace, contact, agent)`
6. Return the result dict directly (success/failure info)
7. Handle `Exception` → 500 with log

**Response schema:**
```json
{"success": true, "message": "Reminder sent", "sent_to": "***-***-1234"}
{"success": false, "message": "Contact has no phone number", "sent_to": null}
```

---

## Frontend

### 4. Add `sendReminder` to `frontend/src/lib/api/appointments.ts`

```typescript
sendReminder: async (
  workspaceId: string,
  appointmentId: number
): Promise<{ success: boolean; message: string; sent_to: string | null }> => {
  const response = await api.post<{ success: boolean; message: string; sent_to: string | null }>(
    `/api/v1/workspaces/${workspaceId}/appointments/${appointmentId}/send-reminder`
  );
  return response.data;
},
```

### 5. Add `SendReminderButton` component in `calendar-page.tsx`

Similar to existing `SyncButton` pattern:
- Props: `appointment`, `workspaceId`, `onSent: () => void`
- Only renders when `appointment.status === 'scheduled'`
- Local `isSending` state
- On click → call `appointmentsApi.sendReminder()`
- On success: `toast.success(`Reminder sent to ${result.sent_to}`)`, then call `onSent()`
- On failure: `toast.error(result.message || "Failed to send reminder")`
- Button icon: `Bell` from lucide-react, shows `Loader2` when sending
- Import `Bell` from lucide-react (add to existing import)

Place in the appointment dialog's action row, next to `SyncButton` and the delete button:
```tsx
{workspaceId && apt.status === "scheduled" && (
  <SendReminderButton
    appointment={apt}
    workspaceId={workspaceId}
    onSent={() => void refetch()}
  />
)}
```

Below the badge/name in the dialog body, show last reminder time if present:
```tsx
{apt.reminder_sent_at && (
  <p className="text-xs text-muted-foreground">
    Last reminder: {format(new Date(apt.reminder_sent_at), "MMM d, h:mm a")}
  </p>
)}
```

### 6. Add reminder button to `contact-sidebar.tsx`

In the appointments section (lines 480-501), for each appointment item that is `status === "scheduled"`, add a small "Send Reminder" icon button inside the appointment row.

- Import `Bell` and add to existing lucide imports
- Import `appointmentsApi` (already imported)
- Local state per-appointment via a `Map<number, boolean>` or simple `Set` tracking sending state
- On click: call `appointmentsApi.sendReminder()`, show toast, invalidate query via `queryClient`

Pattern: use `useMutation` from `@tanstack/react-query` (already imported via `useMutation`).

---

## Implementation Order

1. Create `backend/app/services/calendar/reminder_service.py` (new file)
2. Update `backend/app/workers/reminder_worker.py` (import + delegate to service)
3. Add endpoint to `backend/app/api/v1/appointments.py`
4. Add `sendReminder` to `frontend/src/lib/api/appointments.ts`
5. Update `frontend/src/components/calendar/calendar-page.tsx` (add `SendReminderButton`)
6. Update `frontend/src/components/contacts/contact-sidebar.tsx` (add button to each appointment row)

---

## Verification

- `cd backend && uv run ruff check app && uv run mypy app`
- `cd frontend && npm run lint && npm run build`
- Check reminder_worker still works with refactored service imports
- Test error paths: non-scheduled appointment (400), no phone (graceful error message)

---

## Notes

- The `send_appointment_reminder` in reminder_service uses offset `0` as the "manual" sentinel in `reminders_sent` to track that a manual reminder was sent. This does NOT interfere with the worker's automated offsets (which are always positive: 30, 60, 120, 1440).
- Actually, better to just update `reminder_sent_at` directly without touching `reminders_sent` for manual sends — keeps it clean and doesn't pollute the offset tracking.
- The `ReminderBadges` component already handles `reminder_sent_at` as a fallback, so the manual reminder will display as "Reminder sent" badge after the refetch.
