"""add account_id to categories

Revision ID: 97b7d2db67e0
Revises: b987cbed10f1
Create Date: 2026-01-24 14:59:39.867919

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '97b7d2db67e0'
down_revision: Union[str, Sequence[str], None] = 'b987cbed10f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1) add nullable column first
    op.add_column("categories", sa.Column("account_id", sa.String(length=36), nullable=True))

    # 2) backfill for existing rows
    # Try to map to Office Supplies (best default), else first expense, else any.
    op.execute(
        """
        UPDATE categories c
        SET account_id = COALESCE(
            (
              SELECT a.id
              FROM accounts a
              WHERE a.business_id = c.business_id
                AND a.name = 'Office Supplies'
              ORDER BY a.code NULLS LAST
              LIMIT 1
            ),
            (
              SELECT a.id
              FROM accounts a
              WHERE a.business_id = c.business_id
                AND a.type = 'expense'
              ORDER BY a.code NULLS LAST
              LIMIT 1
            ),
            (
              SELECT a.id
              FROM accounts a
              WHERE a.business_id = c.business_id
              ORDER BY a.code NULLS LAST
              LIMIT 1
            )
        )
        WHERE c.account_id IS NULL;
        """
    )

    # Optional safety check: if any categories still null, raise by forcing NOT NULL will fail.
    # (Leaving it to NOT NULL constraint failure is fine.)

    # 3) make it not null
    op.alter_column("categories", "account_id", existing_type=sa.String(length=36), nullable=False)

    # 4) add FK
    op.create_foreign_key(
        "fk_categories_account_id_accounts",
        source_table="categories",
        referent_table="accounts",
        local_cols=["account_id"],
        remote_cols=["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint("fk_categories_account_id_accounts", "categories", type_="foreignkey")
    op.drop_column("categories", "account_id")