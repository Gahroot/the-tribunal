"""Contact model."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.campaign import CampaignContact
    from app.models.conversation import Conversation
    from app.models.workspace import Workspace


class Contact(Base):
    """CRM contact."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Basic info
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="new", index=True
    )  # new, contacted, qualified, converted, lost
    lead_score: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Organization
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source tracking
    source: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # campaign, inbound_call, manual, api
    source_campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

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
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="contacts")
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="contact", cascade="all, delete-orphan"
    )
    appointments: Mapped[list["Appointment"]] = relationship(
        "Appointment", back_populates="contact", cascade="all, delete-orphan"
    )
    campaign_contacts: Mapped[list["CampaignContact"]] = relationship(
        "CampaignContact", back_populates="contact", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        """Get full name."""
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    def __repr__(self) -> str:
        return f"<Contact(id={self.id}, phone={self.phone_number}, status={self.status})>"
