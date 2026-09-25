"""Extend import candidates for manual post review.

Revision ID: 20260924_0002
Revises: 20260924_0001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260924_0002"
down_revision = "20260924_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("import_candidates", "source_text", new_column_name="raw_text")
    with op.batch_alter_table("import_candidates") as batch:
        batch.add_column(sa.Column("source_account", sa.String(length=200)))
        batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("artist_id", sa.Integer()))
        batch.add_column(sa.Column("candidate_end_at", sa.Time()))
        batch.add_column(sa.Column("candidate_venue_address", sa.String(length=500)))
        batch.add_column(sa.Column("candidate_ticket_url", sa.String(length=2048)))
        batch.add_column(sa.Column("candidate_official_url", sa.String(length=2048)))
        batch.add_column(sa.Column("candidate_stage_name", sa.String(length=200)))
        batch.add_column(sa.Column("parser_version", sa.String(length=50), server_default="legacy", nullable=False))
        batch.add_column(sa.Column("parse_warnings", sa.JSON(), server_default="[]", nullable=False))
        batch.add_column(sa.Column("duplicate_event_id", sa.Integer()))
        batch.add_column(sa.Column("created_event_id", sa.Integer()))
        batch.add_column(sa.Column("review_note", sa.Text()))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False))
        batch.create_foreign_key("fk_import_candidates_artist_id_artists", "artists", ["artist_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_import_candidates_duplicate_event_id_events", "events", ["duplicate_event_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_import_candidates_created_event_id_events", "events", ["created_event_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_import_candidates_artist_id", ["artist_id"])


def downgrade() -> None:
    with op.batch_alter_table("import_candidates") as batch:
        batch.drop_index("ix_import_candidates_artist_id")
        batch.drop_constraint("fk_import_candidates_created_event_id_events", type_="foreignkey")
        batch.drop_constraint("fk_import_candidates_duplicate_event_id_events", type_="foreignkey")
        batch.drop_constraint("fk_import_candidates_artist_id_artists", type_="foreignkey")
        for name in ("updated_at", "review_note", "created_event_id", "duplicate_event_id",
                     "parse_warnings", "parser_version", "candidate_stage_name", "candidate_official_url",
                     "candidate_ticket_url", "candidate_venue_address", "candidate_end_at", "artist_id",
                     "published_at", "source_account"):
            batch.drop_column(name)
    op.alter_column("import_candidates", "raw_text", new_column_name="source_text")
