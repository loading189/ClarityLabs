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
    # Add columns only if missing (Postgres)
    op.execute("ALTER TABLE category_rules ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMP NULL")
    op.execute("ALTER TABLE category_rules ADD COLUMN IF NOT EXISTS last_run_count INTEGER NULL")
    op.execute("ALTER TABLE category_rules ADD COLUMN IF NOT EXISTS last_run_sample JSON NULL")



def downgrade() -> None:
    op.execute("ALTER TABLE category_rules DROP COLUMN IF EXISTS last_run_sample")
    op.execute("ALTER TABLE category_rules DROP COLUMN IF EXISTS last_run_count")
    op.execute("ALTER TABLE category_rules DROP COLUMN IF EXISTS last_run_at")

