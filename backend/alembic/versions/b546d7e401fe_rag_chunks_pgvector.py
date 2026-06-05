"""rag chunks + pgvector

Revision ID: b546d7e401fe
Revises: 7015928a0882
Create Date: 2026-06-05 16:47:03.967488

Adds the pgvector extension and the ``knowledge_chunks`` table that powers
hybrid (vector + keyword) knowledge retrieval. Each chunk carries a
``vector(1536)`` embedding for cosine KNN plus a generated ``tsvector`` column
(GIN-indexed) for full-text keyword search.
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b546d7e401fe"
down_revision: str | None = "7015928a0882"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector extension must exist before the vector column is created.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1536), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_knowledge_chunks_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_chunks_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_knowledge_chunks_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "document_id", "ordinal", name="uq_knowledge_chunks_document_id_ordinal"
        ),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_agent_id"), "knowledge_chunks", ["agent_id"], unique=False
    )
    op.create_index(
        op.f("ix_knowledge_chunks_document_id"),
        "knowledge_chunks",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_chunks_workspace_id"),
        "knowledge_chunks",
        ["workspace_id"],
        unique=False,
    )
    # GIN index powering the keyword (tsvector @@ / ts_rank) retrieval arm.
    op.create_index(
        "ix_knowledge_chunks_search_vector",
        "knowledge_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_search_vector", table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_workspace_id"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_document_id"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_agent_id"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    # Leave the ``vector`` extension installed; other objects may rely on it.
