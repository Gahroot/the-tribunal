"""Field-service models: service locations, crews, and technicians.

These are the operational backbone for ServiceTitan/Jobber-style dispatch in a
home-service workspace:

- :class:`ServiceLocation` — a physical job site belonging to a customer
  (``contact``). One customer may have many locations (primary residence, a
  rental, a commercial unit). Postal address fields are customer PII and are
  Fernet-encrypted at rest via :class:`app.core.encryption.EncryptedString`,
  matching the posture of :class:`app.models.contact.Contact`. Latitude and
  longitude are stored as plain floats because the dispatch map must render pins
  and run geo queries, which encrypted columns cannot support.
- :class:`Crew` — a named field team (a dispatch lane on the schedule board)
  with a display ``color``. Technicians are assigned to at most one crew.
- :class:`Technician` — a field worker. Optionally linked to a :class:`User`
  login (``user_id``) so a technician can sign in to their own schedule, and
  optionally assigned to a :class:`Crew` (``crew_id``). Technician contact
  details are staff data and are stored in plain text, mirroring
  :class:`app.models.bookable_staff.BookableStaff`.

Jobs and visits (which reference these entities) are added by the dispatch layer
in a later migration.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.dialects.postgresql import TEXT as PG_TEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.encryption import EncryptedString
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.contact import Contact
    from app.models.user import User
    from app.models.workspace import Workspace


class ServiceLocation(Base):
    """A physical job site owned by a customer within a workspace."""

    __tablename__ = "service_locations"
    __table_args__ = (
        Index(
            "ix_service_locations_workspace_contact",
            "workspace_id",
            "contact_id",
        ),
        Index(
            "ix_service_locations_workspace_active",
            "workspace_id",
            "is_active",
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
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Human label for the site, e.g. "Main House" or "Rental — 12 Oak St".
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Postal address — customer PII, Fernet-encrypted at rest. Not SQL-queryable;
    # dispatch filtering keys off crew/technician/date rather than address text.
    address_line1: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    city: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    state: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    country: Mapped[str] = mapped_column(
        String(2), nullable=False, default="US", server_default="US"
    )

    # Plain floats so the dispatch map can render pins / run geo queries.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Site access details (gate codes, pets, parking). Sensitive — encrypted.
    access_notes: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships. ``workspace`` is bidirectional (workspace-owned entity);
    # ``contact`` is one-directional to avoid widening the encrypted Contact
    # model (cf. Appointment.bookable_staff).
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="service_locations")
    contact: Mapped["Contact"] = relationship("Contact")

    def __repr__(self) -> str:
        return f"<ServiceLocation(id={self.id}, contact_id={self.contact_id}, name={self.name})>"


class Crew(Base):
    """A named field team that appears as a dispatch lane on the schedule."""

    __tablename__ = "crews"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_crews_workspace_name"),
        Index("ix_crews_workspace_active", "workspace_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Lane color on the dispatch board (hex, e.g. "#6366f1").
    color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#6366f1", server_default="#6366f1"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="crews")
    technicians: Mapped[list["Technician"]] = relationship("Technician", back_populates="crew")

    def __repr__(self) -> str:
        return f"<Crew(id={self.id}, name={self.name})>"


class Technician(Base):
    """A field worker, optionally linked to a login and assigned to a crew."""

    __tablename__ = "technicians"
    __table_args__ = (
        Index("ix_technicians_workspace_active", "workspace_id", "is_active"),
        Index("ix_technicians_workspace_crew", "workspace_id", "crew_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional link to a login so a technician can sign in to their own
    # schedule. SET NULL keeps the technician record if the user is removed.
    # ``users.id`` is an integer PK (see app.models.user.User).
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # A technician belongs to at most one crew; unassigned when null.
    crew_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crews.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Staff identity/contact — plain text, mirroring BookableStaff.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Skill tags for skill-based dispatch (case-insensitive matching).
    skills: Mapped[list[str]] = mapped_column(ARRAY(PG_TEXT), default=list, nullable=False)

    # Display color for this technician on the schedule grid.
    color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#0ea5e9", server_default="#0ea5e9"
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="technicians")
    crew: Mapped["Crew | None"] = relationship("Crew", back_populates="technicians")
    # One-directional: a technician may reference a user login without widening
    # the User model with a reverse collection.
    user: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<Technician(id={self.id}, name={self.name}, crew_id={self.crew_id})>"
