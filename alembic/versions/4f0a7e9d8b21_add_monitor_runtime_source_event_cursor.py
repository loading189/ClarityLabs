"""Add newest_event_source_event_id to monitor_runtime.

Revision ID: 4f0a7e9d8b21
Revises: f8a1c2d4e9b0
Create Date: 2025-02-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4f0a7e9d8b21"
down_revision = "f8a1c2d4e9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monitor_runtime",
        sa.Column("newest_event_source_event_id", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("monitor_runtime", "newest_event_source_event_id")
