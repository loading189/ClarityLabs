"""add plaid connection fields

Revision ID: 1b2a6f1a4f33
Revises: f8a1c2d4e9b0
Create Date: 2026-02-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1b2a6f1a4f33"
down_revision = "f8a1c2d4e9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("integration_connections", sa.Column("plaid_access_token", sa.Text(), nullable=True))
    op.add_column("integration_connections", sa.Column("plaid_item_id", sa.String(length=120), nullable=True))
    op.add_column("integration_connections", sa.Column("plaid_environment", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("integration_connections", "plaid_environment")
    op.drop_column("integration_connections", "plaid_item_id")
    op.drop_column("integration_connections", "plaid_access_token")
