"""Add category rule run metadata (idempotent).

Revision ID: 7c1b1d9c0a31
Revises: 5ac69564ef38
Create Date: 2026-02-15 12:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "7c1b1d9c0a31"
down_revision: Union[str, Sequence[str], None] = "5ac69564ef38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table: str, column: str) -> bool:
    return (
        bind.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table
                  AND column_name = :col
                """
            ),
            {"table": table, "col": column},
        ).first()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _column_exists(bind, "category_rules", "last_run_at"):
        op.add_column("category_rules", sa.Column("last_run_at", sa.DateTime(), nullable=True))

    if not _column_exists(bind, "category_rules", "last_run_status"):
        op.add_column("category_rules", sa.Column("last_run_status", sa.String(length=32), nullable=True))

    if not _column_exists(bind, "category_rules", "last_run_summary"):
        op.add_column("category_rules", sa.Column("last_run_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()

    # Drop in reverse order, only if present
    if _column_exists(bind, "category_rules", "last_run_summary"):
        op.drop_column("category_rules", "last_run_summary")
    if _column_exists(bind, "category_rules", "last_run_status"):
        op.drop_column("category_rules", "last_run_status")
    if _column_exists(bind, "category_rules", "last_run_at"):
        op.drop_column("category_rules", "last_run_at")
