"""Add demo requests table.

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2025-01-20 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "o9p0q1r2s3t4"
down_revision: str | None = "n8o9p0q1r2s3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create demo_requests table."""
    op.create_table(
        "demo_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("phone_number", sa.String(50), nullable=False),
        sa.Column("request_type", sa.String(20), nullable=False),
        sa.Column("client_ip", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Create indexes for rate limiting queries
    op.create_index(
        "ix_demo_requests_phone_number",
        "demo_requests",
        ["phone_number"],
        unique=False,
    )
    op.create_index(
        "ix_demo_requests_client_ip",
        "demo_requests",
        ["client_ip"],
        unique=False,
    )
    op.create_index(
        "ix_demo_requests_created_at",
        "demo_requests",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop demo_requests table."""
    op.drop_index("ix_demo_requests_created_at", table_name="demo_requests")
    op.drop_index("ix_demo_requests_client_ip", table_name="demo_requests")
    op.drop_index("ix_demo_requests_phone_number", table_name="demo_requests")
    op.drop_table("demo_requests")
