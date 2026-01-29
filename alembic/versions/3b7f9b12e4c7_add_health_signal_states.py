"""add health signal states

Revision ID: 3b7f9b12e4c7
Revises: 620795993094
Create Date: 2025-02-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3b7f9b12e4c7"
down_revision = "620795993094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_signal_states",
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("signal_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("business_id", "signal_id"),
    )
    op.create_index(
        "ix_health_signal_states_business_id",
        "health_signal_states",
        ["business_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_health_signal_states_business_id", table_name="health_signal_states")
    op.drop_table("health_signal_states")
