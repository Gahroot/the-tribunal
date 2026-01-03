"""Offer schemas for API validation."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.schemas.lead_magnet import LeadMagnetResponse


class DiscountType(str, Enum):
    """Discount type options."""

    PERCENTAGE = "percentage"
    FIXED = "fixed"
    FREE_SERVICE = "free_service"


class GuaranteeType(str, Enum):
    """Guarantee type options."""

    MONEY_BACK = "money_back"
    SATISFACTION = "satisfaction"
    RESULTS = "results"


class UrgencyType(str, Enum):
    """Urgency type options."""

    LIMITED_TIME = "limited_time"
    LIMITED_QUANTITY = "limited_quantity"
    EXPIRING = "expiring"


class ValueStackItem(BaseModel):
    """Value stack item for Hormozi-style offers."""

    name: str
    description: str | None = None
    value: float = Field(ge=0)
    included: bool = True


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

    # Hormozi-style fields
    headline: str | None = Field(default=None, max_length=500)
    subheadline: str | None = None
    regular_price: float | None = Field(default=None, ge=0)
    offer_price: float | None = Field(default=None, ge=0)
    savings_amount: float | None = Field(default=None, ge=0)
    guarantee_type: GuaranteeType | None = None
    guarantee_days: int | None = Field(default=None, ge=0)
    guarantee_text: str | None = None
    urgency_type: UrgencyType | None = None
    urgency_text: str | None = Field(default=None, max_length=255)
    scarcity_count: int | None = Field(default=None, ge=0)
    value_stack_items: list[ValueStackItem] | None = None
    cta_text: str | None = Field(default=None, max_length=100)
    cta_subtext: str | None = Field(default=None, max_length=255)


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

    # Hormozi-style fields
    headline: str | None = Field(default=None, max_length=500)
    subheadline: str | None = None
    regular_price: float | None = Field(default=None, ge=0)
    offer_price: float | None = Field(default=None, ge=0)
    savings_amount: float | None = Field(default=None, ge=0)
    guarantee_type: GuaranteeType | None = None
    guarantee_days: int | None = Field(default=None, ge=0)
    guarantee_text: str | None = None
    urgency_type: UrgencyType | None = None
    urgency_text: str | None = Field(default=None, max_length=255)
    scarcity_count: int | None = Field(default=None, ge=0)
    value_stack_items: list[ValueStackItem] | None = None
    cta_text: str | None = Field(default=None, max_length=100)
    cta_subtext: str | None = Field(default=None, max_length=255)


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


class OfferCreateWithLeadMagnets(OfferCreate):
    """Schema for creating an offer with lead magnets."""

    lead_magnet_ids: list[uuid.UUID] | None = None


class OfferResponseWithLeadMagnets(OfferResponse):
    """Schema for offer response with attached lead magnets."""

    lead_magnets: list["LeadMagnetResponse"] = []
    total_value: float | None = None  # Computed from value stack + lead magnets


# Import at module level for forward reference resolution
from app.schemas.lead_magnet import LeadMagnetResponse  # noqa: E402, F401

OfferResponseWithLeadMagnets.model_rebuild()
