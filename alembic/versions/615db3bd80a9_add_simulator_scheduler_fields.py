"""add simulator scheduler fields

Revision ID: 615db3bd80a9
Revises: 1209affeeb8f
Create Date: 2026-01-26 20:28:23.742804

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '615db3bd80a9'
down_revision: Union[str, Sequence[str], None] = '1209affeeb8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    # ... keep your other ops in this migration ...

    # Add unique constraint only if it doesn't already exist
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE c.conname = 'uq_business_category_id'
                  AND t.relname = 'business_category_map'
            ) THEN
                ALTER TABLE business_category_map
                ADD CONSTRAINT uq_business_category_id
                UNIQUE (business_id, category_id);
            END IF;
        END $$;
        """
    )



def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE c.conname = 'uq_business_category_id'
                  AND t.relname = 'business_category_map'
            ) THEN
                ALTER TABLE business_category_map
                DROP CONSTRAINT uq_business_category_id;
            END IF;
        END $$;
        """
    )

    # ... keep any other downgrade ops ...

