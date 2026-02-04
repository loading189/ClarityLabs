"""fix category

Revision ID: cd8e5976333f
Revises: 620795993094
Create Date: 2026-01-25 12:33:16.374602
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cd8e5976333f"
down_revision: Union[str, Sequence[str], None] = "620795993094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema.

    This migration historically attempted to create multiple duplicate indexes
    (same table/columns, different names) and can fail when re-run against a DB
    that already has some indexes.

    We make index creation idempotent for PostgreSQL by using:
      CREATE INDEX IF NOT EXISTS ...
    """

    # --- accounts ---
    op.execute("CREATE INDEX IF NOT EXISTS ix_accounts_business_id ON accounts (business_id)")

    # --- business_category_map ---
    # Keep just one canonical set of names (the f() ones) and make them idempotent.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_business_category_map_business_id "
        "ON business_category_map (business_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_business_category_map_category_id "
        "ON business_category_map (category_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_business_category_map_system_key "
        "ON business_category_map (system_key)"
    )

    # NOTE: We intentionally DO NOT also create:
    #   ix_bcm_business_id / ix_bcm_category_id / ix_bcm_system_key
    # because they are duplicates by column and create confusion + collisions.

    # --- categories ---
    op.execute("CREATE INDEX IF NOT EXISTS ix_categories_account_id ON categories (account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_categories_business_id ON categories (business_id)")

    # --- category_rules ---
    op.execute("CREATE INDEX IF NOT EXISTS ix_category_rules_business_id ON category_rules (business_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_category_rules_category_id ON category_rules (category_id)")

    # --- txn_categorizations ---
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_txn_categorizations_business_id "
        "ON txn_categorizations (business_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_txn_categorizations_category_id "
        "ON txn_categorizations (category_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_txncat_source_event_id "
        "ON txn_categorizations (source_event_id)"
    )

    # NOTE: We intentionally DO NOT also create ix_txncat_business_id because
    # it's a duplicate of ix_txn_categorizations_business_id (same column).

    # --- unique constraint (business_id, source_event_id) ---
    # Use an idempotent check so re-runs don't fail.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_txncat_business_sourceevent'
            ) THEN
                ALTER TABLE txn_categorizations
                ADD CONSTRAINT uq_txncat_business_sourceevent
                UNIQUE (business_id, source_event_id);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """
    Downgrade schema.

    Best-effort: drop the constraint and the indexes we create in upgrade().
    """
    # Drop unique constraint if it exists
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_txncat_business_sourceevent'
            ) THEN
                ALTER TABLE txn_categorizations
                DROP CONSTRAINT uq_txncat_business_sourceevent;
            END IF;
        END $$;
        """
    )

    # Drop indexes (Postgres IF EXISTS)
    op.execute("DROP INDEX IF EXISTS ix_txncat_source_event_id")
    op.execute("DROP INDEX IF EXISTS ix_txn_categorizations_category_id")
    op.execute("DROP INDEX IF EXISTS ix_txn_categorizations_business_id")

    op.execute("DROP INDEX IF EXISTS ix_category_rules_category_id")
    op.execute("DROP INDEX IF EXISTS ix_category_rules_business_id")

    op.execute("DROP INDEX IF EXISTS ix_categories_business_id")
    op.execute("DROP INDEX IF EXISTS ix_categories_account_id")

    op.execute("DROP INDEX IF EXISTS ix_business_category_map_system_key")
    op.execute("DROP INDEX IF EXISTS ix_business_category_map_category_id")
    op.execute("DROP INDEX IF EXISTS ix_business_category_map_business_id")

    op.execute("DROP INDEX IF EXISTS ix_accounts_business_id")
