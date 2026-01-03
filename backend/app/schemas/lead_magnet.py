"""Lead magnet schemas for API validation."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class LeadMagnetType(str, Enum):
    """Types of lead magnets."""

    PDF = "pdf"
    VIDEO = "video"
    CHECKLIST = "checklist"
    TEMPLATE = "template"
    WEBINAR = "webinar"
    FREE_TRIAL = "free_trial"
    CONSULTATION = "consultation"
    EBOOK = "ebook"
    MINI_COURSE = "mini_course"


class DeliveryMethod(str, Enum):
    """How the lead magnet is delivered."""

    EMAIL = "email"
    DOWNLOAD = "download"
    REDIRECT = "redirect"
    SMS = "sms"


class LeadMagnetBase(BaseModel):
    """Base lead magnet schema."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    magnet_type: LeadMagnetType = LeadMagnetType.PDF
    delivery_method: DeliveryMethod = DeliveryMethod.EMAIL
    content_url: str = Field(..., max_length=500)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    estimated_value: float | None = Field(default=None, ge=0)
    is_active: bool = True


class LeadMagnetCreate(LeadMagnetBase):
    """Schema for creating a lead magnet."""

    pass


class LeadMagnetUpdate(BaseModel):
    """Schema for updating a lead magnet."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    magnet_type: LeadMagnetType | None = None
    delivery_method: DeliveryMethod | None = None
    content_url: str | None = Field(default=None, max_length=500)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    estimated_value: float | None = Field(default=None, ge=0)
    is_active: bool | None = None


class LeadMagnetResponse(LeadMagnetBase):
    """Schema for lead magnet response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    download_count: int
    created_at: datetime
    updated_at: datetime


class PaginatedLeadMagnets(BaseModel):
    """Paginated lead magnets response."""

    items: list[LeadMagnetResponse]
    total: int
    page: int
    page_size: int
    pages: int


class OfferLeadMagnetCreate(BaseModel):
    """Schema for attaching a lead magnet to an offer."""

    lead_magnet_id: uuid.UUID
    sort_order: int = 0
    is_bonus: bool = True


class OfferLeadMagnetResponse(BaseModel):
    """Schema for offer-lead magnet association response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    offer_id: uuid.UUID
    lead_magnet_id: uuid.UUID
    sort_order: int
    is_bonus: bool
    created_at: datetime
    lead_magnet: LeadMagnetResponse
