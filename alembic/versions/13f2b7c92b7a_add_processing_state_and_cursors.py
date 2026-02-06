"""add processing state and integration cursors

Revision ID: 13f2b7c92b7a
Revises: 9c7b4a6f2a1b
Create Date: 2026-02-06 23:15:30.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "13f2b7c92b7a"
down_revision = "9c7b4a6f2a1b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("integration_connections", sa.Column("last_cursor", sa.String(length=200), nullable=True))
    op.add_column("integration_connections", sa.Column("last_cursor_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("integration_connections", sa.Column("last_webhook_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("integration_connections", sa.Column("last_ingest_counts", sa.JSON(), nullable=True))

    op.create_table(
        "processing_event_states",
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("source_event_id", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("normalized_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("business_id", "source_event_id"),
    )
    op.create_index(
        "ix_processing_event_states_business_status",
        "processing_event_states",
        ["business_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_processing_event_states_business_updated",
        "processing_event_states",
        ["business_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_processing_event_states_business_updated", table_name="processing_event_states")
    op.drop_index("ix_processing_event_states_business_status", table_name="processing_event_states")
    op.drop_table("processing_event_states")

    op.drop_column("integration_connections", "last_ingest_counts")
    op.drop_column("integration_connections", "last_webhook_at")
    op.drop_column("integration_connections", "last_cursor_at")
    op.drop_column("integration_connections", "last_cursor")
