"""SQLAlchemy models for the ``offers`` block.

Two tables — ``offers`` and ``offer_lead_magnets`` — bind to the shared declarative
``Base`` so they register in ``Base.metadata`` and Alembic autogenerate/``check``
can see them. The host imports this module (via the back-compat shims in
``app.models.offer`` / ``app.models.offer_lead_magnet``, which re-export these
classes) before running migrations, so the tables are discovered by
``app.db.model_registry.import_model_modules`` exactly as before.

Core comes in only through the shared ``app.db`` substrate (the declarative
``Base``); sibling-block models (``Workspace``/``Campaign``/``LeadMagnet``) are
referenced by string in relationships, never imported across a block boundary at
runtime. The bidirectional ``Offer`` ↔ ``OfferLeadMagnet`` ↔ ``LeadMagnet``
relationship (lead-capture block) is resolved at mapper configuration time by
class name, so it works as long as the host registers the lead-capture models in
the same ``Base`` (it does, via ``app.models``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.campaign import Campaign
    from app.models.lead_magnet import LeadMagnet
    from app.models.workspace import Workspace


class Offer(Base):
    """Reusable offer/promotion for campaigns."""

    __tablename__ = "offers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Offer details
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Discount configuration
    discount_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="percentage"
    )  # percentage, fixed, free_service
    discount_value: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    # Additional details
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Validity
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Hormozi-style offer fields
    headline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    subheadline: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Pricing for value anchoring
    regular_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    offer_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    savings_amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Guarantee
    guarantee_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    guarantee_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    guarantee_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Urgency and scarcity
    urgency_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    urgency_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scarcity_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Value stack items (JSON array of {name, description, value, included})
    value_stack_items: Mapped[list[dict[str, str | float | bool]] | None] = mapped_column(
        JSONB, default=list, nullable=True
    )

    # Structured offer metadata for product ladders and autonomous sales strategy.
    package_options: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB, default=list, nullable=True
    )
    negotiation_sequence: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB, default=list, nullable=True
    )
    strategy_metadata: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=dict, nullable=True
    )

    # Call to action
    cta_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cta_subtext: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Public landing page fields
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    public_slug: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    require_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    require_phone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_name: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Public page analytics
    page_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opt_ins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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
    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="offers")
    campaigns: Mapped[list[Campaign]] = relationship("Campaign", back_populates="offer")
    offer_lead_magnets: Mapped[list[OfferLeadMagnet]] = relationship(
        "OfferLeadMagnet", back_populates="offer", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Offer(id={self.id}, name={self.name}, discount_type={self.discount_type})>"


class OfferLeadMagnet(Base):
    """Association between offers and lead magnets for value stacking."""

    __tablename__ = "offer_lead_magnets"
    __table_args__ = (UniqueConstraint("offer_id", "lead_magnet_id", name="uq_offer_lead_magnet"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_magnet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead_magnets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Ordering and display
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_bonus: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # Relationships
    offer: Mapped[Offer] = relationship("Offer", back_populates="offer_lead_magnets")
    lead_magnet: Mapped[LeadMagnet] = relationship(
        "LeadMagnet", back_populates="offer_lead_magnets"
    )

    def __repr__(self) -> str:
        return f"<OfferLeadMagnet(offer_id={self.offer_id}, lead_magnet_id={self.lead_magnet_id})>"
