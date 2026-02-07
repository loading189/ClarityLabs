"""Add integration connections and raw event guards.

Revision ID: 9d7e4d8b2f5a
Revises: d6e303265d55
Create Date: 2025-02-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9d7e4d8b2f5a"
down_revision = "7c1b1d9c0a31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("raw_events") as batch:
        batch.add_column(sa.Column("canonical_source_event_id", sa.String(length=120), nullable=True))
        batch.create_unique_constraint(
            "uq_raw_events_business_source_event",
            ["business_id", "source", "source_event_id"],
        )
        batch.create_index(
            "ix_raw_events_canonical_source_event_id",
            ["canonical_source_event_id"],
        )

    op.create_table(
        "integration_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=24), nullable=False, server_default=sa.text("'connected'")),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_cursor", sa.String(length=255), nullable=True),
        sa.Column("last_ingested_source_event_id", sa.String(length=120), nullable=True),
        sa.Column("last_processed_source_event_id", sa.String(length=120), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("business_id", "provider", name="uq_integration_connection_business_provider"),
    )
    op.create_index(
        "ix_integration_connections_business_id",
        "integration_connections",
        ["business_id"],
    )

    op.create_table(
        "integration_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("run_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'ok'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("before_counts", sa.JSON(), nullable=True),
        sa.Column("after_counts", sa.JSON(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_integration_runs_business_id", "integration_runs", ["business_id"])
    op.create_index("ix_integration_runs_started_at", "integration_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_integration_runs_started_at", table_name="integration_runs")
    op.drop_index("ix_integration_runs_business_id", table_name="integration_runs")
    op.drop_table("integration_runs")

    op.drop_index("ix_integration_connections_business_id", table_name="integration_connections")
    op.drop_table("integration_connections")

    with op.batch_alter_table("raw_events") as batch:
        batch.drop_index("ix_raw_events_canonical_source_event_id")
        batch.drop_constraint("uq_raw_events_business_source_event", type_="unique")
        batch.drop_column("canonical_source_event_id")
