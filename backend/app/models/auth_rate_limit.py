"""Auth rate limit model for tracking authentication attempts."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthRateLimit(Base):
    """Track authentication requests for IP-based rate limiting."""

    __tablename__ = "auth_rate_limits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_ip: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "login", "register", "refresh"

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<AuthRateLimit(id={self.id}, ip={self.client_ip}, "
            f"endpoint={self.endpoint})>"
        )
