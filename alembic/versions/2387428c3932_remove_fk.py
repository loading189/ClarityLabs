"""Remove business_category_map.system_key FK (idempotent).

Revision ID: 2387428c3932
Revises: cd8e5976333f
Create Date: 2026-01-25 12:40:43.408307
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "2387428c3932"
down_revision: Union[str, Sequence[str], None] = "cd8e5976333f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _constraint_exists(bind, name: str) -> bool:
    return (
        bind.execute(
            text(
                """
                SELECT 1
                FROM pg_constraint
                WHERE conname = :name
                """
            ),
            {"name": name},
        ).first()
        is not None
    )


def upgrade() -> None:
    """Drop FK if it exists (safe to re-run)."""
    bind = op.get_bind()

    fk_name = "business_category_map_system_key_fkey"

    if _constraint_exists(bind, fk_name):
        op.drop_constraint(
            fk_name,
            "business_category_map",
            type_="foreignkey",
        )


def downgrade() -> None:
    """Recreate FK if missing."""
    bind = op.get_bind()

    fk_name = "business_category_map_system_key_fkey"

    if not _constraint_exists(bind, fk_name):
        op.create_foreign_key(
            fk_name,
            "business_category_map",
            "system_categories",
            ["system_key"],
            ["key"],
            ondelete="CASCADE",
        )
