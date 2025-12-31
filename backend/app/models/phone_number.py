"""Phone number model."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.workspace import Workspace


class PhoneNumber(Base):
    """Telnyx phone number assigned to a workspace."""

    __tablename__ = "phone_numbers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Phone number
    phone_number: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )  # E.164 format
    friendly_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Telnyx identifiers
    telnyx_phone_number_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telnyx_messaging_profile_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Capabilities
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mms_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Agent assignment
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

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
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="phone_numbers")
    assigned_agent: Mapped["Agent | None"] = relationship(
        "Agent", back_populates="phone_numbers"
    )

    def __repr__(self) -> str:
        return f"<PhoneNumber(id={self.id}, number={self.phone_number})>"
