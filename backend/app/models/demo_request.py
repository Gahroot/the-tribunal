"""Demo request model for rate limiting."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DemoRequest(Base):
    """Track demo requests for rate limiting."""

    __tablename__ = "demo_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    request_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "call" or "text"
    client_ip: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, initiated, failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<DemoRequest(id={self.id}, phone={self.phone_number}, "
            f"type={self.request_type}, status={self.status})>"
        )
