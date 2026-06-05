"""Schemas for the Reviews & Reputation engine."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums (mirror the ORM StrEnums for OpenAPI clarity)
# ---------------------------------------------------------------------------


class ReviewSourceSchema(StrEnum):
    """Review origin."""

    SMS_REQUEST = "sms_request"
    GOOGLE = "google"
    FACEBOOK = "facebook"
    MANUAL = "manual"


class ReviewSentimentSchema(StrEnum):
    """Sentiment bucket."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class ReviewStatusSchema(StrEnum):
    """Operator triage state."""

    NEW = "new"
    REPLIED = "replied"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReviewRequestStatusSchema(StrEnum):
    """Review-request lifecycle."""

    PENDING = "pending"
    SENT = "sent"
    CLICKED = "clicked"
    RATED = "rated"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Reputation settings (stored in workspace.settings["review_settings"])
# ---------------------------------------------------------------------------


class ReviewSettings(BaseModel):
    """Per-workspace reputation engine configuration."""

    enabled: bool = False
    # Auto-send a review request when an appointment is marked completed.
    auto_request_on_completion: bool = True
    # Minimum star rating (1-5) that routes to the public review site.
    # Ratings below this go to the private feedback firewall.
    positive_threshold: int = Field(default=4, ge=1, le=5)
    # Public review destinations.
    google_review_url: str | None = Field(default=None, max_length=2000)
    facebook_review_url: str | None = Field(default=None, max_length=2000)
    # SMS body; supports {first_name}, {business_name}, {link} placeholders.
    request_message_template: str | None = Field(default=None, max_length=1000)
    business_name: str | None = Field(default=None, max_length=255)
    # Delay (minutes) after completion before the request fires.
    request_delay_minutes: int = Field(default=60, ge=0, le=10080)
    # Voice/brand guidance fed to the AI reply drafter.
    reply_tone: str | None = Field(default=None, max_length=500)


class ReviewSettingsUpdate(BaseModel):
    """Partial update for reputation settings."""

    enabled: bool | None = None
    auto_request_on_completion: bool | None = None
    positive_threshold: int | None = Field(default=None, ge=1, le=5)
    google_review_url: str | None = Field(default=None, max_length=2000)
    facebook_review_url: str | None = Field(default=None, max_length=2000)
    request_message_template: str | None = Field(default=None, max_length=1000)
    business_name: str | None = Field(default=None, max_length=255)
    request_delay_minutes: int | None = Field(default=None, ge=0, le=10080)
    reply_tone: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


class ReviewResponse(BaseModel):
    """A collected review or private feedback item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    contact_id: int | None = None
    review_request_id: uuid.UUID | None = None
    rating: int
    body: str | None = None
    reviewer_name: str | None = None
    source: ReviewSourceSchema
    sentiment: ReviewSentimentSchema
    status: ReviewStatusSchema
    is_public: bool
    reply_draft: str | None = None
    reply_sent: bool
    replied_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    # Populated from the contact relationship for the operator UI.
    contact_name: str | None = None


class PaginatedReviews(BaseModel):
    """Paginated reviews list."""

    items: list[ReviewResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ReviewCreate(BaseModel):
    """Manually create a review (operator entry)."""

    rating: int = Field(..., ge=1, le=5)
    body: str | None = Field(default=None, max_length=5000)
    reviewer_name: str | None = Field(default=None, max_length=255)
    contact_id: int | None = None
    source: ReviewSourceSchema = ReviewSourceSchema.MANUAL
    is_public: bool = False


class ReviewUpdate(BaseModel):
    """Update a review's triage state or reply draft."""

    status: ReviewStatusSchema | None = None
    reply_draft: str | None = Field(default=None, max_length=5000)
    reply_sent: bool | None = None


# ---------------------------------------------------------------------------
# Review requests
# ---------------------------------------------------------------------------


class ReviewRequestResponse(BaseModel):
    """An outbound review request."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    contact_id: int
    appointment_id: int | None = None
    agent_id: uuid.UUID | None = None
    token: str
    channel: str
    status: ReviewRequestStatusSchema
    rating: int | None = None
    sent_at: datetime | None = None
    clicked_at: datetime | None = None
    rated_at: datetime | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    contact_name: str | None = None


class PaginatedReviewRequests(BaseModel):
    """Paginated review-request list."""

    items: list[ReviewRequestResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ReviewRequestCreate(BaseModel):
    """Create + dispatch a review request for a contact."""

    contact_id: int
    appointment_id: int | None = None
    # Send the SMS immediately. When False the request is created in 'pending'.
    send_now: bool = True


class ReviewRequestSendResult(BaseModel):
    """Result of attempting to dispatch a review request."""

    success: bool
    review_request_id: uuid.UUID | None = None
    status: ReviewRequestStatusSchema
    message: str
    detail: str | None = None


# ---------------------------------------------------------------------------
# AI reply drafting
# ---------------------------------------------------------------------------


class ReviewReplyGenerateRequest(BaseModel):
    """Request body for AI reply drafting."""

    # Optional override of workspace brand voice for this draft.
    tone: str | None = Field(default=None, max_length=500)


class GeneratedReviewReply(BaseModel):
    """AI-generated review reply draft."""

    success: bool
    error: str | None = None
    reply: str | None = None


# ---------------------------------------------------------------------------
# Reputation dashboard
# ---------------------------------------------------------------------------


class RatingBucket(BaseModel):
    """Count of reviews at a given star rating."""

    rating: int
    count: int


class ReputationSummary(BaseModel):
    """Aggregate reputation metrics for a workspace dashboard."""

    average_rating: float = 0.0
    total_reviews: int = 0
    public_reviews: int = 0
    private_feedback: int = 0
    new_count: int = 0
    # Reputation score 0-100 derived from average rating and volume.
    reputation_score: int = 0
    rating_distribution: list[RatingBucket] = Field(default_factory=list)
    # Review-request funnel.
    requests_sent: int = 0
    requests_rated: int = 0
    response_rate: float = 0.0


# ---------------------------------------------------------------------------
# Public (no-auth) review landing page
# ---------------------------------------------------------------------------


class PublicReviewRequest(BaseModel):
    """Public view of a review request for the rating landing page."""

    token: str
    status: ReviewRequestStatusSchema
    rating: int | None = None
    business_name: str | None = None
    contact_first_name: str | None = None
    # Threshold and destinations the client needs to render the gate.
    positive_threshold: int = 4
    already_submitted: bool = False


class PublicRatingSubmit(BaseModel):
    """Recipient submits a star rating on the public landing page."""

    rating: int = Field(..., ge=1, le=5)


class PublicRatingResult(BaseModel):
    """Routing result after a public rating submission (the rating gate)."""

    success: bool
    rating: int
    is_positive: bool
    # When positive, the public review site to redirect to (may be null if the
    # workspace has not configured one — client then shows a thank-you).
    redirect_url: str | None = None
    # When negative, the client renders the private feedback form.
    show_feedback_form: bool = False
    message: str


class PublicFeedbackSubmit(BaseModel):
    """Recipient submits private feedback (low rating firewall)."""

    body: str = Field(..., min_length=1, max_length=5000)
    reviewer_name: str | None = Field(default=None, max_length=255)


class PublicFeedbackResult(BaseModel):
    """Result of submitting private feedback."""

    success: bool
    message: str
