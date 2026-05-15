"""Add missing FK column indexes across models.

Revision ID: a9b0c1d2e3f4
Revises: z8a9b0c1d2e3
Create Date: 2026-05-15 12:00:00.000000

Adds indexes to foreign key columns that were missing them. FK columns
without indexes cause slow lookups, slow cascading deletes, and lock
contention. These indexes match `index=True` markers added to the ORM
models in the same commit.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9b0c1d2e3f4"
down_revision: str | None = "z8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (index_name, table_name, column_name)
_INDEXES: list[tuple[str, str, str]] = [
    ("ix_call_feedback_user_id", "call_feedback", "user_id"),
    ("ix_email_events_workspace_id", "email_events", "workspace_id"),
    ("ix_email_events_message_id", "email_events", "message_id"),
    ("ix_human_nudges_assigned_to_user_id", "human_nudges", "assigned_to_user_id"),
    (
        "ix_improvement_suggestions_source_version_id",
        "improvement_suggestions",
        "source_version_id",
    ),
    (
        "ix_improvement_suggestions_reviewed_by_id",
        "improvement_suggestions",
        "reviewed_by_id",
    ),
    (
        "ix_improvement_suggestions_created_version_id",
        "improvement_suggestions",
        "created_version_id",
    ),
    ("ix_invitations_invited_by_id", "invitations", "invited_by_id"),
    ("ix_lead_magnet_leads_source_offer_id", "lead_magnet_leads", "source_offer_id"),
    ("ix_message_tests_winning_variant_id", "message_tests", "winning_variant_id"),
    (
        "ix_message_tests_converted_to_campaign_id",
        "message_tests",
        "converted_to_campaign_id",
    ),
    ("ix_opportunities_closed_by_id", "opportunities", "closed_by_id"),
    ("ix_opportunity_activities_user_id", "opportunity_activities", "user_id"),
    ("ix_opportunity_contacts_opportunity_id", "opportunity_contacts", "opportunity_id"),
    ("ix_opportunity_contacts_contact_id", "opportunity_contacts", "contact_id"),
    ("ix_pending_actions_reviewed_by_id", "pending_actions", "reviewed_by_id"),
    ("ix_prompt_versions_created_by_id", "prompt_versions", "created_by_id"),
    ("ix_prompt_versions_parent_version_id", "prompt_versions", "parent_version_id"),
    ("ix_contact_tags_contact_id", "contact_tags", "contact_id"),
    ("ix_contact_tags_tag_id", "contact_tags", "tag_id"),
]


def upgrade() -> None:
    for index_name, table_name, column_name in _INDEXES:
        op.create_index(index_name, table_name, [column_name])


def downgrade() -> None:
    for index_name, table_name, _ in reversed(_INDEXES):
        op.drop_index(index_name, table_name=table_name)
