"""add tick runs table

Revision ID: 5e2a1d9f7c3b
Revises: 6f8a2c1d9b44
Create Date: 2026-02-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5e2a1d9f7c3b"
down_revision = "6f8a2c1d9b44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tick_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("bucket", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "bucket", name="uq_tick_runs_business_bucket"),
    )
    op.create_index("ix_tick_runs_business_finished", "tick_runs", ["business_id", "finished_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tick_runs_business_finished", table_name="tick_runs")
    op.drop_table("tick_runs")
