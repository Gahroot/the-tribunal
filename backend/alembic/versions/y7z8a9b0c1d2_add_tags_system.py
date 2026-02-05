"""Add tags system with Tag model and ContactTag join table.

Revision ID: y7z8a9b0c1d2
Revises: x8y9z0a1b2c3
Create Date: 2026-02-05 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "y7z8a9b0c1d2"
down_revision: str | None = "x8y9z0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create tags table
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(7), nullable=False, server_default="#6366f1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_tags_workspace_name"),
    )
    op.create_index("ix_tags_workspace_id", "tags", ["workspace_id"])

    # Create contact_tags join table
    op.create_table(
        "contact_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contact_id", "tag_id", name="uq_contact_tags_contact_tag"),
    )
    op.create_index("ix_contact_tags_contact_id", "contact_tags", ["contact_id"])
    op.create_index("ix_contact_tags_tag_id", "contact_tags", ["tag_id"])

    # Migrate existing array tags data into the new tables
    # 1. Extract unique (workspace_id, tag_name) pairs and insert into tags table
    op.execute("""
        INSERT INTO tags (id, workspace_id, name, color, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            c.workspace_id,
            unnested.tag_name,
            '#6366f1',
            NOW(),
            NOW()
        FROM (
            SELECT DISTINCT workspace_id, unnest(tags) AS tag_name
            FROM contacts
            WHERE tags IS NOT NULL AND array_length(tags, 1) > 0
        ) AS unnested
        JOIN contacts c ON c.workspace_id = unnested.workspace_id
        GROUP BY c.workspace_id, unnested.tag_name
        ON CONFLICT (workspace_id, name) DO NOTHING
    """)

    # 2. Populate contact_tags join table from the array data
    op.execute("""
        INSERT INTO contact_tags (id, contact_id, tag_id, created_at)
        SELECT
            gen_random_uuid(),
            c.id,
            t.id,
            NOW()
        FROM contacts c
        CROSS JOIN LATERAL unnest(c.tags) AS tag_name
        JOIN tags t ON t.workspace_id = c.workspace_id AND t.name = tag_name
        WHERE c.tags IS NOT NULL AND array_length(c.tags, 1) > 0
        ON CONFLICT (contact_id, tag_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("ix_contact_tags_tag_id", table_name="contact_tags")
    op.drop_index("ix_contact_tags_contact_id", table_name="contact_tags")
    op.drop_table("contact_tags")
    op.drop_index("ix_tags_workspace_id", table_name="tags")
    op.drop_table("tags")
