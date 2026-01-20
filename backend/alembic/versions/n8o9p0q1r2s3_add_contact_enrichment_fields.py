"""Add contact enrichment fields.

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2025-01-19 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n8o9p0q1r2s3"
down_revision: str | None = "m7n8o9p0q1r2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add enrichment fields to contacts table."""
    op.add_column(
        "contacts",
        sa.Column("website_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("linkedin_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("business_intel", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("enrichment_status", sa.String(20), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create index for enrichment worker queries
    op.create_index(
        "ix_contacts_enrichment_status",
        "contacts",
        ["enrichment_status"],
        unique=False,
    )


def downgrade() -> None:
    """Remove enrichment fields from contacts table."""
    op.drop_index("ix_contacts_enrichment_status", table_name="contacts")
    op.drop_column("contacts", "enriched_at")
    op.drop_column("contacts", "enrichment_status")
    op.drop_column("contacts", "business_intel")
    op.drop_column("contacts", "linkedin_url")
    op.drop_column("contacts", "website_url")
