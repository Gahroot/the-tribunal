"""Offer schemas for API validation."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DiscountType(str, Enum):
    """Discount type options."""

    PERCENTAGE = "percentage"
    FIXED = "fixed"
    FREE_SERVICE = "free_service"


class OfferBase(BaseModel):
    """Base offer schema."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    discount_type: DiscountType = DiscountType.PERCENTAGE
    discount_value: float = Field(default=0, ge=0)
    terms: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool = True


class OfferCreate(OfferBase):
    """Schema for creating an offer."""

    pass


class OfferUpdate(BaseModel):
    """Schema for updating an offer."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    discount_type: DiscountType | None = None
    discount_value: float | None = Field(default=None, ge=0)
    terms: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool | None = None


class OfferResponse(OfferBase):
    """Schema for offer response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PaginatedOffers(BaseModel):
    """Paginated offers response."""

    items: list[OfferResponse]
    total: int
    page: int
    page_size: int
    pages: int
