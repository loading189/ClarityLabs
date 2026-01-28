"""system categories mapping

Revision ID: 620795993094
Revises: 97b7d2db67e0
Create Date: 2026-01-25 08:22:17.570783

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision = "620795993094"
down_revision = "97b7d2db67e0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_categories",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("group", sa.String(length=64), nullable=True),
    )

    op.create_table(
        "business_category_map",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("business_id", sa.String(length=36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("system_key", sa.String(length=64), sa.ForeignKey("system_categories.key", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.String(length=36), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("business_id", "system_key", name="uq_business_system_key"),
    )

    # IMPORTANT: fix table name here too
    op.alter_column("categories", "account_id", existing_type=sa.String(length=36), nullable=False)


def downgrade():
    op.alter_column("categories", "account_id", existing_type=sa.String(length=36), nullable=True)
    op.drop_table("business_category_map")
    op.drop_table("system_categories")
