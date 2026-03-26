# Schema Refactor Plan: Move Inline Pydantic Schemas to `schemas/`

## Current Status Assessment

After reading all schema files and route files, most of the migration is **already done**. Only 4 route files still have issues:

| Route File | Status | Issues |
|---|---|---|
| `agents.py` | ✅ DONE | Already imports from `schemas/agent.py` |
| `calls.py` | ✅ DONE | Already imports from `schemas/call.py` |
| `dashboard.py` | ✅ DONE | Already imports from `schemas/dashboard.py` |
| `campaign_reports.py` | ✅ DONE | Already imports from `schemas/campaign_report.py` |
| `demo.py` | ✅ DONE | Already imports from `schemas/demo.py` |
| `phone_numbers.py` | ✅ DONE | Already imports from `schemas/phone_number.py` |
| `improvement_suggestions.py` | ✅ DONE | Already imports from `schemas/improvement_suggestion.py` |
| `device_tokens.py` | ✅ DONE | Already imports from `schemas/device_token.py` |
| `workspaces.py` | ✅ DONE | Already imports from `schemas/workspace.py` |
| `appointments.py` | ❌ BROKEN | Has duplicate imports + inline class definitions that shadow schema imports |
| `automations.py` | ❌ NEEDS WORK | Has `AutomationStatsResponse` inline (not yet in `schemas/automation.py`) |
| `contacts.py` | ❌ BROKEN | Has inline classes + mid-file import error + corrupted file end |
| `embed.py` | ❌ NEEDS WORK | Has inline classes identical to `schemas/embed.py`, but doesn't import from there |

---

## Detailed Analysis

### `appointments.py` — BROKEN (duplicate definitions + double router init)
**Issues:**
- Lines 13–18: First import block from `schemas.appointment` (correct)  
- Lines 19–24: **Duplicate** of lines 13–18 (entire import block repeated)
- Lines 37–38: First `router = APIRouter()` and `logger = structlog.get_logger()`
- Lines 44–82: **Inline class definitions** (`AppointmentOverallStats`, `AppointmentAgentStat`, `AppointmentCampaignStat`, `AppointmentStatsResponse`) that shadow the imported ones
- Lines 98–99: **Second** `router = APIRouter()` and `logger = structlog.get_logger()`

All 4 classes already exist identically in `schemas/appointment.py`.

**Fix:** Remove duplicate imports, inline class definitions, and duplicate router/logger init.

---

### `automations.py` — NEEDS WORK
**Issues:**
- `AutomationStatsResponse` is defined inline (lines 25–30)
- Not yet present in `schemas/automation.py`

**Fix:** Add `AutomationStatsResponse` to `schemas/automation.py`, then import it in `automations.py`.

---

### `contacts.py` — BROKEN (syntax errors + corrupted file)
**Issues:**
1. Inline class definitions: `SendMessageToContactRequest`, `MessageResponse`, `ContactIdsResponse`, `AIToggleRequest`, `AIToggleResponse`, `TimelineItem`, `ImportResult`, `CSVPreviewResponse`, `QualifyContactResponse`, `BatchQualifyResponse`
2. **Line 271**: Mid-file `from app.schemas.contact import BulkDeleteRequest, BulkDeleteResponse` — these names DON'T exist in `schemas/contact.py` yet → `ImportError` at startup
3. **Line 272**: Leading space before `@router.post` → `IndentationError`
4. **Lines 754–763**: Corrupted/garbage code appended at end of file

**Fix:** 
- Add all missing schemas to `schemas/contact.py`
- Completely rewrite `contacts.py` with clean top-level imports and no inline classes

---

### `embed.py` — NEEDS WORK
**Issues:**
- Lines 35–109: Inline definitions of `EmbedConfigResponse`, `TokenRequest`, `TokenResponse`, `ChatRequest`, `ChatResponse`, `ToolCallRequest`, `TranscriptRequest`, `EmbedPhoneRequest`
- All 8 classes already exist identically in `schemas/embed.py`
- `embed.py` does not import from `schemas/embed.py`

**Fix:** Remove inline classes, add `from app.schemas.embed import ...`.

---

## Implementation Order

### Step 1: Update `backend/app/schemas/contact.py`
Add the following schemas (after the existing ones):
```python
# Needs additional imports: ConfigDict already implied by existing imports
# Add to existing imports: ConfigDict

class SendMessageToContactRequest(BaseModel):
    body: str
    from_number: str | None = None

class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    direction: str
    channel: str
    body: str
    status: str
    is_ai: bool
    agent_id: uuid.UUID | None
    sent_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ContactIdsResponse(BaseModel):
    ids: list[int]
    total: int

class BulkDeleteRequest(BaseModel):
    ids: list[int]

class BulkDeleteResponse(BaseModel):
    deleted: int
    failed: int
    errors: list[str]

class AIToggleRequest(BaseModel):
    enabled: bool

class AIToggleResponse(BaseModel):
    ai_enabled: bool
    conversation_id: uuid.UUID

class TimelineItem(BaseModel):
    id: uuid.UUID
    type: str
    timestamp: datetime
    direction: str | None = None
    is_ai: bool = False
    content: str
    duration_seconds: int | None = None
    recording_url: str | None = None
    transcript: str | None = None
    status: str | None = None
    booking_outcome: str | None = None
    original_id: uuid.UUID
    original_type: str
    model_config = ConfigDict(from_attributes=True)

class ImportErrorDetail(BaseModel):
    row: int
    field: str | None = None
    error: str = ""

class ImportResult(BaseModel):
    total_rows: int
    successful: int
    failed: int
    skipped_duplicates: int
    errors: list[ImportErrorDetail]
    created_contacts: list[ContactResponse]

class CSVPreviewResponse(BaseModel):
    headers: list[str]
    sample_rows: list[dict[str, str]]
    suggested_mapping: dict[str, str | None]
    contact_fields: list[dict[str, Any]]

class QualifyContactResponse(BaseModel):
    success: bool
    contact_id: int | None = None
    lead_score: int = 0
    is_qualified: bool = False
    qualification_signals: QualificationSignals | None = None
    has_appointment: bool = False
    response_rate: float = 0.0
    message: str | None = None
    error: str | None = None

class BatchQualifyResponse(BaseModel):
    success: bool
    analyzed: int = 0
    qualified: int = 0
    errors: int = 0
    contacts: list[dict[str, Any]] = []
    error: str | None = None
```

**Note:** `schemas/contact.py` already imports `uuid`, `datetime`, `Any` — need to add `ConfigDict` to imports.

### Step 2: Update `backend/app/schemas/automation.py`
Add `AutomationStatsResponse` at end:
```python
class AutomationStatsResponse(BaseModel):
    """Automation statistics response."""
    total: int
    active: int
    triggered_today: int
```

### Step 3: Fix `backend/app/api/v1/appointments.py`
Remove:
- Duplicate import block (lines 19–24)
- Inline class definitions (lines 44–82)
- Duplicate `router = APIRouter()` and `logger = structlog.get_logger()` (lines 98–99)
- `from pydantic import BaseModel` (no longer needed)

Keep only the first set of imports that already imports from schemas.

### Step 4: Fix `backend/app/api/v1/automations.py`
- Remove `from pydantic import BaseModel` import
- Remove inline `AutomationStatsResponse` class (lines 25–30)
- Add `AutomationStatsResponse` to the existing `from app.schemas.automation import ...` block

### Step 5: Fix `backend/app/api/v1/contacts.py` — Full rewrite
- Remove `from pydantic import BaseModel, ConfigDict` from top-level imports (after move)
- Update `from app.schemas.contact import ...` to include all moved schemas
- Remove ALL inline class definitions
- Remove the mid-file import at line 271
- Fix the leading space on line 272
- Remove the corrupted garbage at lines 754–763
- Keep `from app.services.contacts.contact_import import CONTACT_FIELDS, ImportErrorDetail` removed (ImportErrorDetail now defined in schemas, CONTACT_FIELDS still needed)

Wait — `CONTACT_FIELDS` is still used in the `preview_import_csv` endpoint. Keep that import. But `ImportErrorDetail` from services is no longer needed since we define it in schemas/contact.py.

### Step 6: Fix `backend/app/api/v1/embed.py`
- Remove inline class definitions (lines 35–109)
- Add `from app.schemas.embed import (EmbedConfigResponse, TokenRequest, TokenResponse, ChatRequest, ChatResponse, ToolCallRequest, TranscriptRequest, EmbedPhoneRequest)`
- Remove `from pydantic import BaseModel, field_validator` from imports (field_validator no longer needed in this file)

### Step 7: Verify
```bash
cd backend && uv run ruff check app && uv run mypy app
```

---

## Risk Notes

- **`contacts.py` is currently broken** (ImportError + IndentationError + corrupted end). Fix is safe since it restores correct behavior.
- **`appointments.py` has duplicate router init** — removing the second one is safe since `router` is already assigned.
- The `ImportResult` schema in contacts.py uses `ImportErrorDetail` from services — I'll create a matching Pydantic schema in `schemas/contact.py` instead of importing from services. The service returns dataclasses, and Pydantic v2 will coerce them correctly.
- `BulkDeleteResponse` shape: the contacts.py code does `BulkDeleteResponse(**result)` where `result` comes from `service.bulk_delete_contacts()`. Need to verify the service returns `{deleted, failed, errors}` or `{deleted, errors}`.
