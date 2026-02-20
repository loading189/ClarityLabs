"""add case next_review_at

Revision ID: 2d7d9f61c2aa
Revises: 9f3a1d2c4b6e
Create Date: 2026-02-20 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "2d7d9f61c2aa"
down_revision = "9f3a1d2c4b6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "next_review_at")
