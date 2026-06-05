"""add reviews and review_requests

Revision ID: 7015928a0882
Revises: 20260605_agent_transfer
Create Date: 2026-06-05

Adds the Reviews & Reputation engine tables:

- review_requests: outbound "how did we do?" asks tied to a completed
  appointment/contact, with a public landing-page token and rating-gate state.
- reviews: collected reviews and private feedback (negative-feedback firewall),
  with AI reply drafting and operator triage status.

Hand-written to contain only these two tables (autogenerate also reports
pre-existing index/type drift in the live DB that is out of scope here).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7015928a0882"
down_revision: str | Sequence[str] | None = "20260605_agent_transfer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create review_requests and reviews tables."""
    op.create_table(
        "review_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=False),
        sa.Column("appointment_id", sa.BigInteger(), nullable=True),
        sa.Column("agent_id", sa.UUID(), nullable=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column(
            "channel",
            sa.Enum("sms", name="reviewrequestchannel", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                "clicked",
                "rated",
                "completed",
                "failed",
                name="reviewrequeststatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("short_link_id", sa.UUID(), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["short_link_id"], ["short_links.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_review_requests_agent_id"), "review_requests", ["agent_id"], unique=False
    )
    op.create_index(
        op.f("ix_review_requests_appointment_id"),
        "review_requests",
        ["appointment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_review_requests_contact_id"), "review_requests", ["contact_id"], unique=False
    )
    op.create_index(
        op.f("ix_review_requests_status"), "review_requests", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_review_requests_token"), "review_requests", ["token"], unique=True
    )
    op.create_index(
        op.f("ix_review_requests_workspace_id"),
        "review_requests",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_requests_workspace_status",
        "review_requests",
        ["workspace_id", "status"],
        unique=False,
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.BigInteger(), nullable=True),
        sa.Column("review_request_id", sa.UUID(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("reviewer_name", sa.String(length=255), nullable=True),
        sa.Column(
            "source",
            sa.Enum(
                "sms_request",
                "google",
                "facebook",
                "manual",
                name="reviewsource",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column(
            "sentiment",
            sa.Enum(
                "positive",
                "neutral",
                "negative",
                name="reviewsentiment",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "replied",
                "resolved",
                "dismissed",
                name="reviewstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("reply_draft", sa.Text(), nullable=True),
        sa.Column("reply_sent", sa.Boolean(), nullable=False),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["review_request_id"], ["review_requests.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reviews_contact_id"), "reviews", ["contact_id"], unique=False)
    op.create_index(op.f("ix_reviews_sentiment"), "reviews", ["sentiment"], unique=False)
    op.create_index(op.f("ix_reviews_status"), "reviews", ["status"], unique=False)
    op.create_index(op.f("ix_reviews_workspace_id"), "reviews", ["workspace_id"], unique=False)
    op.create_index(
        "ix_reviews_workspace_public", "reviews", ["workspace_id", "is_public"], unique=False
    )
    op.create_index(
        "ix_reviews_workspace_status", "reviews", ["workspace_id", "status"], unique=False
    )


def downgrade() -> None:
    """Drop reviews and review_requests tables."""
    op.drop_index("ix_reviews_workspace_status", table_name="reviews")
    op.drop_index("ix_reviews_workspace_public", table_name="reviews")
    op.drop_index(op.f("ix_reviews_workspace_id"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_status"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_sentiment"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_contact_id"), table_name="reviews")
    op.drop_table("reviews")

    op.drop_index("ix_review_requests_workspace_status", table_name="review_requests")
    op.drop_index(op.f("ix_review_requests_workspace_id"), table_name="review_requests")
    op.drop_index(op.f("ix_review_requests_token"), table_name="review_requests")
    op.drop_index(op.f("ix_review_requests_status"), table_name="review_requests")
    op.drop_index(op.f("ix_review_requests_contact_id"), table_name="review_requests")
    op.drop_index(op.f("ix_review_requests_appointment_id"), table_name="review_requests")
    op.drop_index(op.f("ix_review_requests_agent_id"), table_name="review_requests")
    op.drop_table("review_requests")
