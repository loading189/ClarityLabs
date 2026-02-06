"""add integration connections and vendor category map

Revision ID: 9c7b4a6f2a1b
Revises: 4f0a7e9d8b21
Create Date: 2026-02-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9c7b4a6f2a1b"
down_revision = "4f0a7e9d8b21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "provider", name="uq_integration_connection_business_provider"),
    )
    op.create_index("ix_integration_connections_business_id", "integration_connections", ["business_id"], unique=False)
    op.create_index("ix_integration_connections_provider", "integration_connections", ["provider"], unique=False)

    op.create_table(
        "vendor_category_map",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("vendor_key", sa.String(length=160), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "vendor_key", name="uq_vendor_category_map_business_vendor"),
    )
    op.create_index("ix_vendor_category_map_business_id", "vendor_category_map", ["business_id"], unique=False)
    op.create_index("ix_vendor_category_map_vendor_key", "vendor_category_map", ["vendor_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vendor_category_map_vendor_key", table_name="vendor_category_map")
    op.drop_index("ix_vendor_category_map_business_id", table_name="vendor_category_map")
    op.drop_table("vendor_category_map")

    op.drop_index("ix_integration_connections_provider", table_name="integration_connections")
    op.drop_index("ix_integration_connections_business_id", table_name="integration_connections")
    op.drop_table("integration_connections")
