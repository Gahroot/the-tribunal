"""SQLAlchemy models for the ``reviews`` block.

Two tables — ``reviews`` and ``review_requests`` — bind to the shared
declarative ``Base`` so they register in ``Base.metadata`` and Alembic
autogenerate/``check`` can see them. The host imports this module (via the
back-compat shims in ``app.models.review`` / ``app.models.review_request``,
which re-export these classes) before running migrations, so the tables are
discovered by ``app.db.model_registry.import_model_modules`` exactly as before.

Core comes in only through the shared ``app.db`` substrate (the declarative
``Base``); sibling-block models (``Contact``/``Appointment``/``Workspace``) are
referenced by string in relationships, never imported across a block boundary.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.contact import Contact
    from app.models.workspace import Workspace


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


class ReviewSource(StrEnum):
    """Where a review originated."""

    SMS_REQUEST = "sms_request"  # collected via a review-request SMS landing page
    GOOGLE = "google"
    FACEBOOK = "facebook"
    MANUAL = "manual"  # entered by an operator


class ReviewSentiment(StrEnum):
    """Coarse sentiment bucket derived from the rating."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class ReviewStatus(StrEnum):
    """Operator-facing triage state of a review."""

    NEW = "new"
    REPLIED = "replied"
    RESOLVED = "resolved"  # private feedback actioned/closed
    DISMISSED = "dismissed"


class Review(Base):
    """A collected review or private feedback item for a workspace."""

    __tablename__ = "reviews"
    __table_args__ = (
        Index("ix_reviews_workspace_status", "workspace_id", "status"),
        Index("ix_reviews_workspace_public", "workspace_id", "is_public"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    review_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_requests.id", ondelete="SET NULL"),
        nullable=True,
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    source: Mapped[ReviewSource] = mapped_column(
        SAEnum(
            ReviewSource,
            native_enum=False,
            create_constraint=False,
            length=30,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ReviewSource.SMS_REQUEST,
    )
    sentiment: Mapped[ReviewSentiment] = mapped_column(
        SAEnum(
            ReviewSentiment,
            native_enum=False,
            create_constraint=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ReviewSentiment.NEUTRAL,
        index=True,
    )
    status: Mapped[ReviewStatus] = mapped_column(
        SAEnum(
            ReviewStatus,
            native_enum=False,
            create_constraint=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ReviewStatus.NEW,
        index=True,
    )

    # True => high rating routed to a public review site (positive testimonial).
    # False => low rating captured privately (negative-feedback firewall).
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Operator/AI reply drafting.
    reply_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    workspace: Mapped[Workspace] = relationship("Workspace")
    contact: Mapped[Contact | None] = relationship("Contact")
    review_request: Mapped[ReviewRequest | None] = relationship(
        "ReviewRequest", back_populates="review"
    )

    def __repr__(self) -> str:
        return (
            f"<Review(id={self.id}, rating={self.rating}, "
            f"sentiment={self.sentiment}, is_public={self.is_public})>"
        )


# ---------------------------------------------------------------------------
# ReviewRequest
# ---------------------------------------------------------------------------


def generate_review_token() -> str:
    """Return a URL-safe token for a public review-request landing page."""
    return secrets.token_urlsafe(24)


class ReviewRequestStatus(StrEnum):
    """Lifecycle of a review request."""

    PENDING = "pending"  # created, not yet sent
    SENT = "sent"  # SMS dispatched
    CLICKED = "clicked"  # recipient opened the landing page
    RATED = "rated"  # recipient picked a star rating
    COMPLETED = "completed"  # routed to public review or private feedback captured
    FAILED = "failed"  # send failed (no phone, opted out, provider error)


class ReviewRequestChannel(StrEnum):
    """Delivery channel for a review request."""

    SMS = "sms"


class ReviewRequest(Base):
    """An outbound review-request ask tied to a completed appointment/contact."""

    __tablename__ = "review_requests"
    __table_args__ = (
        Index(
            "ix_review_requests_workspace_status",
            "workspace_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Public landing-page token (unguessable, indexed for O(1) lookup).
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, default=generate_review_token
    )

    channel: Mapped[ReviewRequestChannel] = mapped_column(
        SAEnum(
            ReviewRequestChannel,
            native_enum=False,
            create_constraint=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ReviewRequestChannel.SMS,
    )
    status: Mapped[ReviewRequestStatus] = mapped_column(
        SAEnum(
            ReviewRequestStatus,
            native_enum=False,
            create_constraint=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ReviewRequestStatus.PENDING,
        index=True,
    )

    # Rating chosen by the recipient (1-5), null until they rate.
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Outbound tracking links.
    short_link_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("short_links.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    workspace: Mapped[Workspace] = relationship("Workspace")
    contact: Mapped[Contact] = relationship("Contact")
    appointment: Mapped[Appointment | None] = relationship("Appointment")
    review: Mapped[Review | None] = relationship(
        "Review", back_populates="review_request", uselist=False
    )

    def __repr__(self) -> str:
        return (
            f"<ReviewRequest(id={self.id}, status={self.status}, "
            f"rating={self.rating}, contact_id={self.contact_id})>"
        )


__all__ = [
    "Review",
    "ReviewSource",
    "ReviewSentiment",
    "ReviewStatus",
    "ReviewRequest",
    "ReviewRequestStatus",
    "ReviewRequestChannel",
    "generate_review_token",
]
