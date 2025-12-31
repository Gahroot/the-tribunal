"""AI Agent model."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.campaign import Campaign
    from app.models.conversation import Conversation, Message
    from app.models.phone_number import PhoneNumber
    from app.models.workspace import Workspace


class Agent(Base):
    """AI agent for voice and text conversations."""

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Basic info
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Channel configuration
    channel_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="both"
    )  # voice, text, both

    # Voice configuration
    voice_provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="openai"
    )  # openai, elevenlabs
    voice_id: Mapped[str] = mapped_column(
        String(100), nullable=False, default="alloy"
    )  # alloy, shimmer, nova, or ElevenLabs voice ID
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en-US")

    # OpenAI Realtime settings
    turn_detection_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="server_vad"
    )
    turn_detection_threshold: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    silence_duration_ms: Mapped[int] = mapped_column(Integer, default=500, nullable=False)

    # LLM settings
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)

    # Greeting
    initial_greeting: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Text agent settings
    text_response_delay_ms: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    text_max_context_messages: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    # Cal.com integration
    calcom_event_type_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Tools enabled
    enabled_tools: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=["book_appointment"], nullable=False
    )
    tool_settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Stats (denormalized)
    total_calls: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_messages: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

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
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="agents")
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="assigned_agent", foreign_keys="Conversation.assigned_agent_id"
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="agent", foreign_keys="Message.agent_id"
    )
    campaigns: Mapped[list["Campaign"]] = relationship("Campaign", back_populates="agent")
    appointments: Mapped[list["Appointment"]] = relationship("Appointment", back_populates="agent")
    phone_numbers: Mapped[list["PhoneNumber"]] = relationship(
        "PhoneNumber", back_populates="assigned_agent"
    )

    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, name={self.name}, channel={self.channel_mode})>"
