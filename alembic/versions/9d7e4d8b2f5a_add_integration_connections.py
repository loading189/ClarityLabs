"""Add integration connections and raw event guards (idempotent).

Revision ID: 9d7e4d8b2f5a
Revises: 7c1b1d9c0a31
Create Date: 2026-02-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9d7e4d8b2f5a"
down_revision: Union[str, Sequence[str], None] = "7c1b1d9c0a31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    return (
        bind.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :name
                """
            ),
            {"name": name},
        ).first()
        is not None
    )


def _index_exists(bind, name: str) -> bool:
    return (
        bind.execute(
            text(
                """
                SELECT 1
                FROM pg_class c
                WHERE c.relkind = 'i'
                  AND c.relname = :name
                """
            ),
            {"name": name},
        ).first()
        is not None
    )


def _constraint_exists(bind, name: str) -> bool:
    return (
        bind.execute(
            text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
            {"name": name},
        ).first()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()

    # --- integration_connections table ---
    if not _table_exists(bind, "integration_connections"):
        op.create_table(
            "integration_connections",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("business_id", sa.String(length=36), nullable=False),
            sa.Column("provider", sa.String(length=40), nullable=False),

            sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("status", sa.String(length=24), server_default=sa.text("'connected'"), nullable=False),
            sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),

            sa.Column("provider_cursor", sa.String(length=255), nullable=True),
            sa.Column("last_ingested_source_event_id", sa.String(length=120), nullable=True),
            sa.Column("last_processed_source_event_id", sa.String(length=120), nullable=True),

            sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", postgresql.JSON(astext_type=sa.Text()), nullable=True),

            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),

            sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    # Ensure the unique constraint exists (even if table pre-existed)
    uq_name = "uq_integration_connection_business_provider"
    if not _constraint_exists(bind, uq_name):
        op.create_unique_constraint(
            uq_name,
            "integration_connections",
            ["business_id", "provider"],
        )

    # Helpful index for lookups (optional, but safe)
    if not _index_exists(bind, "ix_integration_connections_business_id"):
        op.create_index(
            "ix_integration_connections_business_id",
            "integration_connections",
            ["business_id"],
            unique=False,
        )

    # --- raw_events uniqueness guard (if this migration includes it in your branch) ---
    # If your repo expects a uniqueness constraint on (business_id, source, source_event_id),
    # add it safely here. If you already added it elsewhere, this will no-op.
    raw_uq = "uq_raw_events_business_source_source_event"
    if _table_exists(bind, "raw_events") and not _constraint_exists(bind, raw_uq):
        op.create_unique_constraint(
            raw_uq,
            "raw_events",
            ["business_id", "source", "source_event_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Drop raw_events uq (best effort)
    raw_uq = "uq_raw_events_business_source_source_event"
    if _constraint_exists(bind, raw_uq):
        op.drop_constraint(raw_uq, "raw_events", type_="unique")

    # Drop indexes/constraints on integration_connections (best effort)
    if _index_exists(bind, "ix_integration_connections_business_id"):
        op.drop_index("ix_integration_connections_business_id", table_name="integration_connections")

    uq_name = "uq_integration_connection_business_provider"
    if _constraint_exists(bind, uq_name):
        op.drop_constraint(uq_name, "integration_connections", type_="unique")

    # Drop table if it exists
    if _table_exists(bind, "integration_connections"):
        op.execute("DROP TABLE IF EXISTS integration_connections CASCADE")
