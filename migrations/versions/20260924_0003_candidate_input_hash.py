"""Add a stable idempotency hash to imported candidates.

Revision ID: 20260924_0003
Revises: 20260924_0002
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260924_0003"
down_revision = "20260924_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("import_candidates") as batch:
        batch.add_column(sa.Column("input_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("external_id", sa.String(length=100), nullable=True))
        batch.create_index("ix_import_candidates_input_hash", ["input_hash"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("import_candidates") as batch:
        batch.drop_index("ix_import_candidates_input_hash")
        batch.drop_column("external_id")
        batch.drop_column("input_hash")
