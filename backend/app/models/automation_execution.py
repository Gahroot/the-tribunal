"""AutomationExecution model — tracks which contacts have been processed per automation."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.automation import Automation
    from app.models.automation_event import AutomationEvent
    from app.models.contact import Contact


class AutomationExecution(Base):
    """Records that a contact was processed by an automation.

    Dedupe is keyed two ways via partial unique indexes:

    * **Polling triggers** (``event_id IS NULL``) are unique per
      (automation, contact) so a contact is processed at most once per
      automation — the original contact-centric behaviour.
    * **Event triggers** (``event_id IS NOT NULL``) are unique per
      (automation, event) so each emitted domain event runs an automation at
      most once, while still allowing the same contact to be processed for
      repeated events (e.g. a deal moving stage twice).

    A ``status`` field lets delayed/scheduled executions carry state across
    poll cycles.
    """

    __tablename__ = "automation_executions"
    __table_args__ = (
        Index(
            "uq_automation_execution_contact",
            "automation_id",
            "contact_id",
            unique=True,
            postgresql_where=text("event_id IS NULL"),
        ),
        Index(
            "uq_automation_execution_event",
            "automation_id",
            "event_id",
            unique=True,
            postgresql_where=text("event_id IS NOT NULL"),
        ),
        Index(
            "ix_automation_executions_status_scheduled_for",
            "status",
            "scheduled_for",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    automation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("automations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Set for event-triggered executions; NULL for polling-trigger executions.
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("automation_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Status: "pending" | "completed" | "failed" | "scheduled"
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)

    # For delayed actions — worker re-checks executions where this is <= now
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Optional error message
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    automation: Mapped["Automation"] = relationship("Automation", back_populates="executions")
    contact: Mapped["Contact | None"] = relationship("Contact")
    event: Mapped["AutomationEvent | None"] = relationship("AutomationEvent")

    def __repr__(self) -> str:
        return (
            f"<AutomationExecution(automation_id={self.automation_id}, "
            f"contact_id={self.contact_id}, status={self.status})>"
        )
