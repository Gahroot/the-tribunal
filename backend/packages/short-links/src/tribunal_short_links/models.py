"""SQLAlchemy models for the ``short-links`` block.

The two tables — ``short_links`` and ``link_clicks`` — bind to the shared
declarative ``Base`` so they register in ``Base.metadata`` and Alembic
autogenerate/``check`` can see them. The host imports this module (via the
back-compat shims in ``app.models.short_link`` / ``app.models.link_click``,
which re-export these classes) before running migrations, so the tables are
discovered by ``app.db.model_registry.import_model_modules`` exactly as before.

Core comes in only through the shared ``app.db`` substrate (the declarative
``Base``); the block carries no sideways import into a sibling block.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShortLink(Base):
    """A shortened URL sent via SMS, used for click tracking."""

    __tablename__ = "short_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    short_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ShortLink(short_code={self.short_code}, clicks={self.click_count})>"


class LinkClick(Base):
    """A single click event on a ShortLink."""

    __tablename__ = "link_clicks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    short_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("short_links.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    referer: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<LinkClick(short_link_id={self.short_link_id}, at={self.clicked_at})>"
