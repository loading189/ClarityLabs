"""remove fk

Revision ID: 2387428c3932
Revises: cd8e5976333f
Create Date: 2026-01-25 12:41:xx.xxxxxx

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2387428c3932"
down_revision: Union[str, Sequence[str], None] = "cd8e5976333f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Drop FK constraint on business_category_map.system_key if it exists.
    Some DBs never had this FK (or it was renamed), so make this idempotent.
    """
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE c.conname = 'business_category_map_system_key_fkey'
                  AND t.relname = 'business_category_map'
            ) THEN
                ALTER TABLE business_category_map
                DROP CONSTRAINT business_category_map_system_key_fkey;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """
    Best-effort restore of the FK (only if it doesn't already exist).

    NOTE: This assumes businesses_category_map.system_key referenced some table
    previously. If the original FK target is different in your schema, adjust here.
    If you don't actually want it restored, you can safely leave downgrade as no-op.
    """
    # If you know the original target table/column, put it back.
    # Leaving as a no-op is safer than guessing the FK target.
    pass
