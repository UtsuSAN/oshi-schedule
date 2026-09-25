"""Create initial schedule schema.

Revision ID: 20260924_0001
Revises:
Create Date: 2026-09-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260924_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200)),
        sa.Column("x_username", sa.String(length=100)),
        sa.Column("x_user_id", sa.String(length=100)),
        sa.Column("official_url", sa.String(length=2048)),
        sa.Column("enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_artists_name", "artists", ["name"])
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("open_at", sa.Time()),
        sa.Column("start_at", sa.Time()),
        sa.Column("end_at", sa.Time()),
        sa.Column("venue_name", sa.String(length=300)),
        sa.Column("venue_address", sa.String(length=500)),
        sa.Column("ticket_url", sa.String(length=2048)),
        sa.Column("official_url", sa.String(length=2048)),
        sa.Column("status", sa.String(length=20), server_default="scheduled", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint("status IN ('scheduled', 'changed', 'cancelled', 'unknown')", name="ck_events_status_valid"),
    )
    op.create_index("ix_events_title", "events", ["title"])
    op.create_index("ix_events_event_date", "events", ["event_date"])
    op.create_table(
        "import_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_url", sa.String(length=2048)),
        sa.Column("source_text", sa.Text()),
        sa.Column("candidate_title", sa.String(length=300)),
        sa.Column("candidate_date", sa.Date()),
        sa.Column("candidate_open_at", sa.Time()),
        sa.Column("candidate_start_at", sa.Time()),
        sa.Column("candidate_venue", sa.String(length=300)),
        sa.Column("candidate_appearance_start", sa.Time()),
        sa.Column("candidate_appearance_end", sa.Time()),
        sa.Column("candidate_benefit_start", sa.Time()),
        sa.Column("candidate_benefit_end", sa.Time()),
        sa.Column("confidence", sa.Float()),
        sa.Column("candidate_type", sa.String(length=30), server_default="unknown", nullable=False),
        sa.Column("review_status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint("candidate_type IN ('new', 'update', 'possible_duplicate', 'unknown')", name="ck_import_candidates_candidate_type_valid"),
        sa.CheckConstraint("review_status IN ('pending', 'approved', 'rejected')", name="ck_import_candidates_review_status_valid"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_import_candidates_confidence_range"),
    )
    op.create_table(
        "appearances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artist_id", sa.Integer(), sa.ForeignKey("artists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("appearance_start_at", sa.Time()),
        sa.Column("appearance_end_at", sa.Time()),
        sa.Column("benefit_start_at", sa.Time()),
        sa.Column("benefit_end_at", sa.Time()),
        sa.Column("stage_name", sa.String(length=200)),
        sa.Column("notes", sa.Text()),
    )
    op.create_index("ix_appearances_event_id", "appearances", ["event_id"])
    op.create_index("ix_appearances_artist_id", "appearances", ["artist_id"])
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(length=20), server_default="manual", nullable=False),
        sa.Column("source_url", sa.String(length=2048)),
        sa.Column("source_account", sa.String(length=200)),
        sa.Column("source_post_id", sa.String(length=100)),
        sa.Column("source_text", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("media_urls", sa.JSON(), nullable=False),
        sa.CheckConstraint("source_type IN ('x', 'manual', 'official_site', 'other')", name="ck_sources_source_type_valid"),
    )
    op.create_index("ix_sources_event_id", "sources", ["event_id"])
    op.create_index("ix_sources_source_post_id", "sources", ["source_post_id"])


def downgrade() -> None:
    op.drop_index("ix_sources_source_post_id", table_name="sources")
    op.drop_index("ix_sources_event_id", table_name="sources")
    op.drop_table("sources")
    op.drop_index("ix_appearances_artist_id", table_name="appearances")
    op.drop_index("ix_appearances_event_id", table_name="appearances")
    op.drop_table("appearances")
    op.drop_table("import_candidates")
    op.drop_index("ix_events_event_date", table_name="events")
    op.drop_index("ix_events_title", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_artists_name", table_name="artists")
    op.drop_table("artists")
