"""Store reviewed event change notices as candidates.

Revision ID: 20260926_0004
Revises: 20260924_0003
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260926_0004"
down_revision = "20260924_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("import_candidates") as batch:
        batch.add_column(sa.Column("change_kind", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("change_summary", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("target_event_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_import_candidates_target_event_id_events", "events", ["target_event_id"], ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_import_candidates_target_event_id", ["target_event_id"])
        batch.create_check_constraint(
            "change_kind_valid",
            "change_kind IS NULL OR change_kind IN ('appearance_cancelled', 'event_cancelled', 'postponed', "
            "'time_changed', 'venue_changed', 'ticket_changed', 'generic_update')",
        )


def downgrade() -> None:
    with op.batch_alter_table("import_candidates") as batch:
        batch.drop_constraint("change_kind_valid", type_="check")
        batch.drop_index("ix_import_candidates_target_event_id")
        batch.drop_constraint("fk_import_candidates_target_event_id_events", type_="foreignkey")
        batch.drop_column("target_event_id")
        batch.drop_column("change_summary")
        batch.drop_column("change_kind")
