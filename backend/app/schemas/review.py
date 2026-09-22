"""Back-compat shim for the Reviews & Reputation schemas.

The schemas were extracted into the mountable ``tribunal-reviews`` block
(``backend/packages/reviews``). The live definitions live in
``tribunal_reviews.schemas``; this module re-exports them so existing imports
(``from app.schemas.review import ReviewSettings``) keep working.
"""

from __future__ import annotations

from tribunal_reviews.schemas import (
    GeneratedReviewReply,
    PaginatedReviewRequests,
    PaginatedReviews,
    PublicFeedbackResult,
    PublicFeedbackSubmit,
    PublicRatingResult,
    PublicRatingSubmit,
    PublicReviewRequest,
    RatingBucket,
    ReputationSummary,
    ReviewCreate,
    ReviewReplyGenerateRequest,
    ReviewRequestCreate,
    ReviewRequestResponse,
    ReviewRequestSendResult,
    ReviewRequestStatusSchema,
    ReviewResponse,
    ReviewSentimentSchema,
    ReviewSettings,
    ReviewSettingsUpdate,
    ReviewSourceSchema,
    ReviewStatusSchema,
    ReviewUpdate,
)

__all__ = [
    "GeneratedReviewReply",
    "PaginatedReviewRequests",
    "PaginatedReviews",
    "PublicFeedbackResult",
    "PublicFeedbackSubmit",
    "PublicRatingResult",
    "PublicRatingSubmit",
    "PublicReviewRequest",
    "RatingBucket",
    "ReputationSummary",
    "ReviewCreate",
    "ReviewReplyGenerateRequest",
    "ReviewRequestCreate",
    "ReviewRequestResponse",
    "ReviewRequestSendResult",
    "ReviewRequestStatusSchema",
    "ReviewResponse",
    "ReviewSentimentSchema",
    "ReviewSettings",
    "ReviewSettingsUpdate",
    "ReviewSourceSchema",
    "ReviewStatusSchema",
    "ReviewUpdate",
]
