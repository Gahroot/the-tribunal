"""Offer model for campaign promotions."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.campaign import Campaign
    from app.models.workspace import Workspace


class Offer(Base):
    """Reusable offer/promotion for campaigns."""

    __tablename__ = "offers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
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
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="offers")
    campaigns: Mapped[list["Campaign"]] = relationship("Campaign", back_populates="offer")

    def __repr__(self) -> str:
        return f"<Offer(id={self.id}, name={self.name}, discount_type={self.discount_type})>"
