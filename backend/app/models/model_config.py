"""Workspace and agent overrides for production AI tasks."""

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True
    )
    task: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    # USD per million tokens. NULL means pricing is unknown, never free.
    input_usd_per_million: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    output_usd_per_million: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "task IN ('voice_llm', 'transcript_analysis', 'caller_memory', "
            "'transcript_judgment', 'prompt_improvement', 'reports')",
            name="ck_model_configs_task",
        ),
        CheckConstraint("length(model) > 0", name="ck_model_configs_model"),
        CheckConstraint(
            "(input_usd_per_million IS NULL AND output_usd_per_million IS NULL) OR "
            "(input_usd_per_million >= 0 AND output_usd_per_million >= 0)",
            name="ck_model_configs_prices",
        ),
        Index(
            "uq_model_configs_workspace_task",
            "workspace_id",
            "task",
            unique=True,
            postgresql_where=text("agent_id IS NULL"),
        ),
        Index(
            "uq_model_configs_agent_task",
            "agent_id",
            "task",
            unique=True,
            postgresql_where=text("agent_id IS NOT NULL"),
        ),
    )
