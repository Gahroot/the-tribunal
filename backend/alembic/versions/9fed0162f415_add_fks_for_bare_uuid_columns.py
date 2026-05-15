"""Add FK constraints + indexes to bare UUID columns for referential integrity.

Covers:
- messages.campaign_id -> campaigns.id (SET NULL)
- campaign_contacts.call_message_id -> messages.id (SET NULL)
- campaign_contacts.sms_fallback_message_id -> messages.id (SET NULL)
- global_opt_outs.source_campaign_id -> campaigns.id (SET NULL)
- global_opt_outs.source_message_id -> messages.id (SET NULL)
- contacts.source_campaign_id -> campaigns.id (SET NULL)

Each FK column also gets a btree index.

Revision ID: 9fed0162f415
Revises: 8d5dbe66cc0d
Create Date: 2026-05-15 16:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9fed0162f415"
down_revision: str | None = "8d5dbe66cc0d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (source_table, column, target_table, fk_name, ix_name)
_FK_SPECS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "messages",
        "campaign_id",
        "campaigns",
        "fk_messages_campaign_id_campaigns",
        "ix_messages_campaign_id",
    ),
    (
        "campaign_contacts",
        "call_message_id",
        "messages",
        "fk_campaign_contacts_call_message_id_messages",
        "ix_campaign_contacts_call_message_id",
    ),
    (
        "campaign_contacts",
        "sms_fallback_message_id",
        "messages",
        "fk_campaign_contacts_sms_fallback_message_id_messages",
        "ix_campaign_contacts_sms_fallback_message_id",
    ),
    (
        "global_opt_outs",
        "source_campaign_id",
        "campaigns",
        "fk_global_opt_outs_source_campaign_id_campaigns",
        "ix_global_opt_outs_source_campaign_id",
    ),
    (
        "global_opt_outs",
        "source_message_id",
        "messages",
        "fk_global_opt_outs_source_message_id_messages",
        "ix_global_opt_outs_source_message_id",
    ),
    (
        "contacts",
        "source_campaign_id",
        "campaigns",
        "fk_contacts_source_campaign_id_campaigns",
        "ix_contacts_source_campaign_id",
    ),
)


def upgrade() -> None:
    # Null out any orphaned references before adding FK constraints so the
    # constraint creation cannot fail on legacy data that points at deleted
    # rows. Each column is already nullable with SET NULL semantics, so this
    # is the natural data-repair step.
    for source_table, column, target_table, _fk, _ix in _FK_SPECS:
        op.execute(
            f"""
            UPDATE {source_table}
            SET {column} = NULL
            WHERE {column} IS NOT NULL
              AND {column} NOT IN (SELECT id FROM {target_table})
            """
        )

    for source_table, column, target_table, fk_name, ix_name in _FK_SPECS:
        op.create_index(ix_name, source_table, [column])
        op.create_foreign_key(
            fk_name,
            source_table,
            target_table,
            [column],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for source_table, _column, _target_table, fk_name, ix_name in _FK_SPECS:
        op.drop_constraint(fk_name, source_table, type_="foreignkey")
        op.drop_index(ix_name, table_name=source_table)
