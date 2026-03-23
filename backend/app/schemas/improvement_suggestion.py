"""Improvement suggestion schemas for prompt improvement endpoints."""

import uuid

from pydantic import BaseModel, ConfigDict


class ImprovementSuggestionResponse(BaseModel):
    """Schema for improvement suggestion response."""

    id: uuid.UUID
    agent_id: uuid.UUID
    source_version_id: uuid.UUID
    suggested_prompt: str
    suggested_greeting: str | None
    mutation_type: str
    analysis_summary: str
    expected_improvement: str | None
    status: str
    reviewed_at: str | None
    reviewed_by_id: int | None
    rejection_reason: str | None
    created_version_id: uuid.UUID | None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class ImprovementSuggestionListResponse(BaseModel):
    """Schema for paginated suggestion list."""

    items: list[ImprovementSuggestionResponse]
    total: int
    page: int
    page_size: int
    pages: int


class RejectSuggestionRequest(BaseModel):
    """Schema for rejecting a suggestion."""

    reason: str | None = None


class GenerateSuggestionsRequest(BaseModel):
    """Schema for generating suggestions."""

    num_suggestions: int = 3


class ApproveResponse(BaseModel):
    """Schema for approve response."""

    suggestion: ImprovementSuggestionResponse
    created_version_id: uuid.UUID
