"""Add health signal states (idempotent).

Revision ID: 3b7f9b12e4c7
Revises: 620795993094
Create Date: 2025-02-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "3b7f9b12e4c7"
down_revision: Union[str, Sequence[str], None] = "620795993094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    return (
        bind.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :name
                """
            ),
            {"name": name},
        ).first()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "health_signal_states"):
        op.create_table(
            "health_signal_states",
            sa.Column("business_id", sa.String(length=36), nullable=False),
            sa.Column("signal_id", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("resolution_note", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("business_id", "signal_id"),
            sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "health_signal_states"):
        op.execute("DROP TABLE IF EXISTS health_signal_states CASCADE")
