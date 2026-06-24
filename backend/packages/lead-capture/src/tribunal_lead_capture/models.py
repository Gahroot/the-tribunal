"""SQLAlchemy models for the ``lead-capture`` block.

Three tables — ``lead_magnets``, ``lead_magnet_leads`` and ``lead_sources`` —
bind to the shared declarative ``Base`` so they register in ``Base.metadata``
and Alembic autogenerate/``check`` can see them. The host imports this module
(via the back-compat shims in ``app.models.lead_magnet`` /
``app.models.lead_magnet_lead`` / ``app.models.lead_source``, which re-export
these classes) before running migrations, so the tables are discovered by
``app.db.model_registry.import_model_modules`` exactly as before.

Core comes in only through the shared ``app.db`` substrate (the declarative
``Base``); sibling-block models (``Workspace``/``Contact``/``Offer``/
``OfferLeadMagnet``) are referenced by string in relationships, never imported
across a block boundary at runtime. The bidirectional ``LeadMagnet`` ↔
``OfferLeadMagnet`` relationship (offers block) is resolved at mapper
configuration time by class name, so it works as long as the host registers the
offers models in the same ``Base`` (it does, via ``app.models``).
"""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.contact import Contact
    from app.models.offer import Offer
    from app.models.offer_lead_magnet import OfferLeadMagnet
    from app.models.workspace import Workspace


class LeadMagnetType(StrEnum):
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


class DeliveryMethod(StrEnum):
    """How the lead magnet is delivered."""

    EMAIL = "email"
    DOWNLOAD = "download"
    REDIRECT = "redirect"
    SMS = "sms"


def generate_lead_source_key() -> str:
    """Generate a short public key for lead source (e.g., ls_xK9mN2pQ)."""
    chars = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(8))
    return f"ls_{random_part}"


class LeadMagnet(Base):
    """Lead magnet/freebie that can be attached to offers as bonuses."""

    __tablename__ = "lead_magnets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Lead magnet details
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Type and delivery
    magnet_type: Mapped[LeadMagnetType] = mapped_column(
        SAEnum(
            LeadMagnetType,
            native_enum=False,
            create_constraint=False,
            length=50,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=LeadMagnetType.PDF,
    )
    delivery_method: Mapped[DeliveryMethod] = mapped_column(
        SAEnum(
            DeliveryMethod,
            native_enum=False,
            create_constraint=False,
            length=50,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=DeliveryMethod.EMAIL,
    )

    # Content
    content_url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Rich content data (for quizzes, calculators, rich text, etc.)
    content_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Value perception (for Hormozi-style value stacking)
    estimated_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Status and tracking
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
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
    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="lead_magnets")
    offer_lead_magnets: Mapped[list[OfferLeadMagnet]] = relationship(
        "OfferLeadMagnet", back_populates="lead_magnet", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<LeadMagnet(id={self.id}, name={self.name}, type={self.magnet_type})>"


class LeadMagnetLead(Base):
    """Track leads captured via lead magnets."""

    __tablename__ = "lead_magnet_leads"
    __table_args__ = (
        Index(
            "ix_lead_magnet_leads_workspace_created_at",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_magnet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead_magnets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Contact information
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Link to CRM contact if created/matched
    contact_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Quiz/Calculator data
    quiz_answers: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    calculator_inputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Delivery tracking
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source tracking
    source_offer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # Relationships
    lead_magnet: Mapped[LeadMagnet] = relationship("LeadMagnet")
    workspace: Mapped[Workspace] = relationship("Workspace")
    contact: Mapped[Contact | None] = relationship("Contact")
    source_offer: Mapped[Offer | None] = relationship("Offer")

    def __repr__(self) -> str:
        return f"<LeadMagnetLead(id={self.id}, email={self.email}, score={self.score})>"


class LeadSource(Base):
    """Configurable lead source for public lead ingestion."""

    __tablename__ = "lead_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Basic info
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    public_key: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True, default=generate_lead_source_key
    )
    allowed_domains: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Post-capture action
    action: Mapped[str] = mapped_column(
        String(50), nullable=False, default="collect"
    )  # collect | auto_text | auto_call | enroll_campaign
    action_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Timestamps
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

    def __repr__(self) -> str:
        return f"<LeadSource(id={self.id}, name={self.name}, action={self.action})>"
