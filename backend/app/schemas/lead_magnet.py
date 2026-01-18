"""Lead magnet schemas for API validation."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

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
    # Rich interactive types
    QUIZ = "quiz"
    CALCULATOR = "calculator"
    RICH_TEXT = "rich_text"
    VIDEO_COURSE = "video_course"


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
    content_url: str = Field(default="", max_length=500)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    estimated_value: float | None = Field(default=None, ge=0)
    content_data: dict[str, Any] | None = None
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
    content_data: dict[str, Any] | None = None
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


# Quiz Generation Schemas
class QuizGenerationRequest(BaseModel):
    """Request schema for AI quiz generation."""

    topic: str = Field(..., min_length=2, max_length=200)
    target_audience: str = Field(..., min_length=2, max_length=500)
    goal: str = Field(..., min_length=2, max_length=500)
    num_questions: int = Field(default=5, ge=3, le=10)


class QuizOption(BaseModel):
    """Quiz question option."""

    id: str
    text: str
    score: int


class QuizQuestion(BaseModel):
    """Quiz question."""

    id: str
    text: str
    type: str  # single_choice, multiple_choice, scale
    options: list[QuizOption] = []
    weight: int | None = None  # For scale type


class QuizResult(BaseModel):
    """Quiz result configuration."""

    id: str
    min_score: int
    max_score: int
    title: str
    description: str
    cta_text: str | None = None


class GeneratedQuizContent(BaseModel):
    """Response schema for generated quiz content."""

    success: bool
    error: str | None = None
    title: str | None = None
    description: str | None = None
    questions: list[QuizQuestion] = []
    results: list[QuizResult] = []


# Calculator Generation Schemas
class CalculatorGenerationRequest(BaseModel):
    """Request schema for AI calculator generation."""

    calculator_type: str = Field(..., min_length=2, max_length=100)
    industry: str = Field(..., min_length=2, max_length=200)
    target_audience: str = Field(..., min_length=2, max_length=500)
    value_proposition: str = Field(..., min_length=2, max_length=500)


class CalculatorSelectOption(BaseModel):
    """Calculator select field option."""

    value: str
    label: str
    multiplier: float | None = None


class CalculatorInput(BaseModel):
    """Calculator input field."""

    id: str
    label: str
    type: str  # number, currency, percentage, select
    placeholder: str | None = None
    default_value: float | None = None
    prefix: str | None = None
    suffix: str | None = None
    help_text: str | None = None
    required: bool = True
    options: list[CalculatorSelectOption] | None = None


class CalculatorCalculation(BaseModel):
    """Intermediate calculation."""

    id: str
    label: str
    formula: str
    format: str  # currency, percentage, number


class CalculatorOutput(BaseModel):
    """Calculator output field."""

    id: str
    label: str
    formula: str
    format: str
    highlight: bool = False
    description: str | None = None


class CalculatorCTA(BaseModel):
    """Calculator call to action."""

    text: str
    description: str | None = None


class GeneratedCalculatorContent(BaseModel):
    """Response schema for generated calculator content."""

    success: bool
    error: str | None = None
    title: str | None = None
    description: str | None = None
    inputs: list[CalculatorInput] = []
    calculations: list[CalculatorCalculation] = []
    outputs: list[CalculatorOutput] = []
    cta: CalculatorCTA | None = None
