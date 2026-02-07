"""add raw event uniqueness and integration lifecycle fields

Revision ID: f4d83a9d1b2c
Revises: 13f2b7c92b7a
Create Date: 2026-02-08 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f4d83a9d1b2c"
down_revision = "13f2b7c92b7a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_raw_events_business_source_event",
        "raw_events",
        ["business_id", "source", "source_event_id"],
    )

    op.add_column(
        "integration_connections",
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "integration_connections",
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "integration_connections",
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "integration_connections",
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "integration_connections",
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "integration_connections",
        sa.Column("last_ingested_source_event_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "integration_connections",
        sa.Column("last_processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "integration_connections",
        sa.Column("last_processed_source_event_id", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("integration_connections", "last_processed_source_event_id")
    op.drop_column("integration_connections", "last_processed_at")
    op.drop_column("integration_connections", "last_ingested_source_event_id")
    op.drop_column("integration_connections", "last_ingested_at")
    op.drop_column("integration_connections", "last_error_at")
    op.drop_column("integration_connections", "last_success_at")
    op.drop_column("integration_connections", "disconnected_at")
    op.drop_column("integration_connections", "is_enabled")

    op.drop_constraint("uq_raw_events_business_source_event", "raw_events", type_="unique")
