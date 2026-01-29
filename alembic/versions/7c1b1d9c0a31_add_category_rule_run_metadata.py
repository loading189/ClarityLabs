"""add category rule run metadata

Revision ID: 7c1b1d9c0a31
Revises: 5ac69564ef38
Create Date: 2026-02-15 12:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7c1b1d9c0a31"
down_revision: Union[str, Sequence[str], None] = "5ac69564ef38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("category_rules", sa.Column("last_run_at", sa.DateTime(), nullable=True))
    op.add_column("category_rules", sa.Column("last_run_updated_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("category_rules", "last_run_updated_count")
    op.drop_column("category_rules", "last_run_at")
