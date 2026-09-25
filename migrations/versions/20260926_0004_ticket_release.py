"""Add optional ticket release date and time."""
from alembic import op
import sqlalchemy as sa

revision = "20260926_0004"
down_revision = "20260924_0003"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("events", sa.Column("ticket_release_date", sa.Date(), nullable=True))
    op.add_column("events", sa.Column("ticket_release_time", sa.Time(), nullable=True))

def downgrade() -> None:
    op.drop_column("events", "ticket_release_time")
    op.drop_column("events", "ticket_release_date")
