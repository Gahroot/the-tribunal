"""add_failed_jobs_dlq

Adds the ``failed_jobs`` dead-letter queue table that ``RetryableWorker``
writes to after exhausting its retry budget. Rows are keyed by
``(worker_name, item_key)`` so repeated terminal failures on the same item
update the existing row (incrementing ``attempts`` and refreshing
``last_failed_at``) rather than piling up duplicates.

Revision ID: dlq01a1b2c3d4
Revises: c9e1a2b3d4f5
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dlq01a1b2c3d4"
down_revision: str | None = "c9e1a2b3d4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FAILED_JOB_STATUS_VALUES = ("pending", "retried", "abandoned")
FAILED_JOB_STATUS_ENUM = "failed_job_status"


def upgrade() -> None:
    failed_job_status = postgresql.ENUM(
        *FAILED_JOB_STATUS_VALUES,
        name=FAILED_JOB_STATUS_ENUM,
        create_type=False,
    )
    failed_job_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "failed_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("worker_name", sa.Text(), nullable=False),
        sa.Column("item_key", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "first_failed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_failed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "status",
            failed_job_status,
            nullable=False,
            server_default="pending",
        ),
        sa.UniqueConstraint("worker_name", "item_key", name="uq_failed_jobs_worker_item"),
    )
    op.create_index(
        "ix_failed_jobs_worker_name_status",
        "failed_jobs",
        ["worker_name", "status"],
    )
    op.create_index(
        "ix_failed_jobs_status_last_failed_at",
        "failed_jobs",
        ["status", "last_failed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_failed_jobs_status_last_failed_at", table_name="failed_jobs")
    op.drop_index("ix_failed_jobs_worker_name_status", table_name="failed_jobs")
    op.drop_table("failed_jobs")
    failed_job_status = postgresql.ENUM(
        *FAILED_JOB_STATUS_VALUES,
        name=FAILED_JOB_STATUS_ENUM,
        create_type=False,
    )
    failed_job_status.drop(op.get_bind(), checkfirst=True)
