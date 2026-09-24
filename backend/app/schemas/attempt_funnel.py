"""Voice attempt funnel response contract."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FunnelMetrics(BaseModel):
    calls: int
    connected: int
    conversations: int
    qualified: int
    booked: int
    shown: int
    connect_rate: float
    conversation_rate: float
    qualified_rate: float
    booked_rate: float
    shown_rate: float
    show_rate_of_booked: float | None
    estimated_cost_usd: float
    estimated_cost_per_call_usd: float
    estimated_cost_per_booked_usd: float | None
    estimated_cost_per_shown_usd: float | None


class AttemptBucket(FunnelMetrics):
    value: int


class HourBucket(FunnelMetrics):
    value: int


class SourceBucket(FunnelMetrics):
    value: str


class CampaignBucket(FunnelMetrics):
    value: UUID
    campaign_name: str


class AttemptFunnelResponse(BaseModel):
    starts_at: datetime
    ends_at: datetime
    hour_timezone: str
    cost_basis: str
    overall: FunnelMetrics
    attempt: list[AttemptBucket]
    hour_utc: list[HourBucket]
    lead_source: list[SourceBucket]
    campaign: list[CampaignBucket]
