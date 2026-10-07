"""Phone number schemas for phone number management endpoints."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PhoneNumberResponse(BaseModel):
    """Phone number response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    phone_number: str
    friendly_name: str | None
    provider: str
    sms_enabled: bool
    voice_enabled: bool
    mms_enabled: bool
    imessage_enabled: bool
    mac_relay_sender_id: str | None
    mac_relay_service: str
    assigned_agent_id: uuid.UUID | None
    is_active: bool


class PaginatedPhoneNumbers(BaseModel):
    """Paginated phone numbers response."""

    items: list[PhoneNumberResponse]
    total: int
    page: int
    page_size: int
    pages: int


class PhoneNumberUpdate(BaseModel):
    """Schema for updating a phone number."""

    friendly_name: str | None = None
    assigned_agent_id: uuid.UUID | None = None
    is_active: bool | None = None


class SearchPhoneNumbersRequest(BaseModel):
    """Search phone numbers request."""

    country: str = "US"
    area_code: str | None = None
    contains: str | None = None
    limit: int = 10


class PurchasePhoneNumberRequest(BaseModel):
    """Purchase phone number request.

    ``assigned_agent_id`` answers inbound calls on the new number. When omitted
    and ``skip_agent_assignment`` is false, the workspace's only eligible voice
    agent is used; with zero or several eligible agents the assignment stays
    pending so the operator chooses explicitly.
    """

    phone_number: str
    assigned_agent_id: uuid.UUID | None = None
    skip_agent_assignment: bool = False


InboundVoiceStatusValue = Literal[
    "ready",
    "needs_agent_choice",
    "no_eligible_agent",
    "agent_not_eligible",
    "voice_disabled",
    "number_inactive",
]


class PhoneNumberInboundReadinessResponse(BaseModel):
    """Whether a new inbound call to this number will be answered by an agent."""

    model_config = ConfigDict(from_attributes=True)

    phone_number_id: uuid.UUID
    status: InboundVoiceStatusValue
    ready: bool
    assigned_agent_id: uuid.UUID | None
    assigned_agent_name: str | None
    eligible_agent_count: int
    message: str
    action_label: str | None = None
    action_href: str | None = None


class EligibleVoiceAgentResponse(BaseModel):
    """An active, voice-capable agent that can answer inbound calls."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    channel_mode: str


class PhoneNumbersInboundReadinessResponse(BaseModel):
    """Inbound voice readiness for the workspace's own numbers."""

    eligible_agents: list[EligibleVoiceAgentResponse]
    numbers: list[PhoneNumberInboundReadinessResponse]


class PhoneNumberPurchaseResponse(PhoneNumberResponse):
    """Purchased number plus how its inbound agent assignment was resolved."""

    agent_assignment: Literal["explicit", "default_single_agent", "skipped", "pending"]
    inbound_voice: PhoneNumberInboundReadinessResponse


class PhoneNumberInfoResponse(BaseModel):
    """Phone number info from Telnyx."""

    id: str
    phone_number: str
    friendly_name: str | None
    capabilities: dict[str, bool] | None


class PhoneNumberTelephonyStatusResponse(BaseModel):
    """Whether workspace telephony actions are available."""

    enabled: bool
    provider: Literal["telnyx"] = "telnyx"
    message: str
    action_label: str | None = None
    action_href: str | None = None


class TelephonyUnavailableDetails(BaseModel):
    """Client action metadata for a telephony-unavailable error."""

    action_label: str
    action_href: str


class TelephonyUnavailableDetail(BaseModel):
    """Actionable error body returned when telephony is unavailable."""

    code: Literal["telephony_unavailable"] = "telephony_unavailable"
    message: str
    details: TelephonyUnavailableDetails
    request_id: str | None = None
