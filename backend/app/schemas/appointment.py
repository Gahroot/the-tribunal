"""Appointment schemas for API validation."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AppointmentBase(BaseModel):
    """Base appointment schema."""

    duration_minutes: int = Field(default=30, ge=15, le=480)
    service_type: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class AppointmentCreate(AppointmentBase):
    """Schema for creating an appointment."""

    contact_id: int
    agent_id: str | None = None
    scheduled_at: datetime


class AppointmentUpdate(BaseModel):
    """Schema for updating an appointment."""

    status: str | None = Field(default=None, pattern="^(scheduled|completed|cancelled|no_show)$")
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    service_type: str | None = None
    notes: str | None = None


class ContactSummary(BaseModel):
    """Minimal contact info for appointments."""

    id: int
    first_name: str
    last_name: str | None
    email: str | None
    # Contacts may have no phone (email-only leads); see 20260925 migration.
    phone_number: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AppointmentResponse(AppointmentBase):
    """Schema for appointment response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: uuid.UUID
    contact_id: int
    contact: ContactSummary | None = None
    agent_id: uuid.UUID | None
    message_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    scheduled_at: datetime
    status: str
    cancellation_reason: str | None = None
    calcom_booking_uid: str | None
    calcom_booking_id: int | None
    calcom_event_type_id: int | None
    sync_status: str
    last_synced_at: datetime | None
    sync_error: str | None = None  # Stored error message from Cal.com sync failures
    deposit_amount_cents: int | None = None
    deposit_status: str | None = None
    deposit_checkout_url: str | None = None
    reminder_sent_at: datetime | None = None
    reminders_sent: list[int] = []
    created_at: datetime
    updated_at: datetime


class AppointmentCancelRequest(BaseModel):
    """Cancel an appointment, including its external calendar booking."""

    reason: str | None = Field(default=None, max_length=500)
    crm_only: bool = Field(
        default=False,
        description=(
            "Mark cancelled in the CRM without touching the external booking. "
            "The external booking stays active (sync_status='local_only')."
        ),
    )


CancelProviderResult = Literal[
    "cancelled",  # provider cancelled the booking on this request
    "already_cancelled",  # provider reported it was already cancelled
    "not_found",  # provider has no booking with this UID
    "skipped",  # crm_only: external booking left active
    "not_applicable",  # appointment has no external booking
]


class AppointmentCancelResponse(BaseModel):
    """Outcome of a cancellation, honest about what happened externally."""

    appointment: AppointmentResponse
    outcome: Literal["cancelled", "already_cancelled"]
    provider: Literal["calcom", "none"]
    provider_result: CancelProviderResult
    attendee_notice: Literal["provider", "none"] = Field(
        description=(
            "'provider' when Cal.com processed the cancellation on this request and sends "
            "its own cancellation notice per the event's settings; 'none' otherwise. "
            "The CRM itself never messages the contact on cancellation."
        )
    )
    message: str


class PaginatedAppointments(BaseModel):
    """Paginated appointments response."""

    items: list[AppointmentResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ---------------------------------------------------------------------------
# Stats response schemas
# ---------------------------------------------------------------------------


class AppointmentOverallStats(BaseModel):
    """Overall appointment statistics for the workspace."""

    total: int
    scheduled: int
    completed: int
    no_show: int
    cancelled: int
    show_up_rate: float


class AppointmentAgentStat(BaseModel):
    """Per-agent appointment statistics."""

    agent_id: str
    agent_name: str
    total: int
    completed: int
    no_show: int
    show_up_rate: float


class AppointmentCampaignStat(BaseModel):
    """Per-campaign appointment statistics."""

    campaign_id: str
    campaign_name: str
    total: int
    completed: int
    no_show: int
    show_up_rate: float


class AppointmentStatsResponse(BaseModel):
    """Full show-up rate analytics response."""

    overall: AppointmentOverallStats
    by_agent: list[AppointmentAgentStat]
    by_campaign: list[AppointmentCampaignStat]
