"""FailedJob model — dead-letter queue for terminally failed worker tasks.

When ``RetryableWorker.execute_with_retry`` exhausts its retry budget, the
terminal failure is recorded here so it can be inspected and replayed by an
operator (see ``backend/scripts/inspect_dlq.py``). Rows are deduped on
``(worker_name, item_key)``: re-failing the same logical item increments
``attempts`` and refreshes ``last_failed_at`` instead of inserting a new row.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Status values match the failed_job_status Postgres enum created in the
# dlq01a1b2c3d4 migration. Stored as plain strings on the ORM side so callers
# don't need to import an enum class for simple updates.
FAILED_JOB_STATUS_PENDING = "pending"
FAILED_JOB_STATUS_RETRIED = "retried"
FAILED_JOB_STATUS_ABANDONED = "abandoned"

FAILED_JOB_STATUSES: tuple[str, ...] = (
    FAILED_JOB_STATUS_PENDING,
    FAILED_JOB_STATUS_RETRIED,
    FAILED_JOB_STATUS_ABANDONED,
)

# Match the Postgres ENUM created in the dlq01a1b2c3d4 migration. We pass
# ``create_type=False`` so SQLAlchemy never tries to CREATE/DROP the type —
# the migration owns its lifecycle.
_FailedJobStatusType = Enum(
    *FAILED_JOB_STATUSES,
    name="failed_job_status",
    create_type=False,
    native_enum=True,
    validate_strings=True,
)


class FailedJob(Base):
    """A worker task that exhausted its retry budget."""

    __tablename__ = "failed_jobs"
    __table_args__ = (
        UniqueConstraint("worker_name", "item_key", name="uq_failed_jobs_worker_item"),
        Index(
            "ix_failed_jobs_worker_name_status",
            "worker_name",
            "status",
        ),
        Index(
            "ix_failed_jobs_status_last_failed_at",
            "status",
            "last_failed_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_name: Mapped[str] = mapped_column(Text, nullable=False)
    item_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    first_failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Stored as the Postgres ``failed_job_status`` enum (see migration).
    # The Python side keeps the value as a plain string for ergonomics.
    status: Mapped[str] = mapped_column(
        _FailedJobStatusType,
        nullable=False,
        default=FAILED_JOB_STATUS_PENDING,
    )

    def __repr__(self) -> str:
        return (
            f"<FailedJob(worker={self.worker_name}, item_key={self.item_key}, "
            f"attempts={self.attempts}, status={self.status})>"
        )
