"""Campaign report schemas for post-mortem intelligence reports."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class CampaignReportResponse(BaseModel):
    """Full campaign report response."""

    id: uuid.UUID
    campaign_id: uuid.UUID
    workspace_id: uuid.UUID
    campaign_name: str | None = None
    campaign_type: str | None = None

    status: str
    error_message: str | None = None

    metrics_snapshot: dict[str, Any] | None = None
    executive_summary: str | None = None
    key_findings: list[dict[str, Any]] | None = None
    what_worked: list[dict[str, Any]] | None = None
    what_didnt_work: list[dict[str, Any]] | None = None
    recommendations: list[dict[str, Any]] | None = None
    segment_analysis: list[dict[str, Any]] | None = None
    timing_analysis: dict[str, Any] | None = None
    prompt_performance: list[dict[str, Any]] | None = None

    generated_suggestion_ids: list[str] | None = None

    generated_at: str | None = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class CampaignReportSummary(BaseModel):
    """Lighter summary for list views."""

    id: uuid.UUID
    campaign_id: uuid.UUID
    campaign_name: str | None = None
    campaign_type: str | None = None
    status: str
    executive_summary: str | None = None
    generated_at: str | None = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class CampaignReportListResponse(BaseModel):
    """Paginated report list."""

    items: list[CampaignReportSummary]
    total: int
    page: int
    page_size: int
    pages: int
