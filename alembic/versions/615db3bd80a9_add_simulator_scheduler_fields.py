"""Add simulator scheduler fields + tighten org cascade (idempotent).

Revision ID: 615db3bd80a9
Revises: 1209affeeb8f
Create Date: 2026-01-26 20:28:23.742804
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "615db3bd80a9"
down_revision: Union[str, Sequence[str], None] = "1209affeeb8f"
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


def _column_exists(bind, table: str, column: str) -> bool:
    return (
        bind.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table
                  AND column_name = :col
                """
            ),
            {"table": table, "col": column},
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
    """Upgrade schema (safe to re-run)."""
    bind = op.get_bind()

    # These tables may or may not exist depending on how simulator migrations landed.
    if _table_exists(bind, "simulator_configs"):
        op.execute("DROP TABLE IF EXISTS simulator_configs CASCADE")
    if _table_exists(bind, "simulator_runs"):
        op.execute("DROP TABLE IF EXISTS simulator_runs CASCADE")

    # Unique constraint on BCM
    if not _constraint_exists(bind, "uq_business_category_id"):
        op.create_unique_constraint(
            "uq_business_category_id",
            "business_category_map",
            ["business_id", "category_id"],
        )

    # Add scenario/story fields (only if missing)
    if _table_exists(bind, "business_integration_profiles"):
        if not _column_exists(bind, "business_integration_profiles", "scenario_id"):
            op.add_column(
                "business_integration_profiles",
                sa.Column(
                    "scenario_id",
                    sa.String(length=80),
                    server_default=sa.text("'restaurant_v1'"),
                    nullable=False,
                ),
            )
        if not _column_exists(bind, "business_integration_profiles", "story_version"):
            op.add_column(
                "business_integration_profiles",
                sa.Column(
                    "story_version",
                    sa.Integer(),
                    server_default=sa.text("1"),
                    nullable=False,
                ),
            )

        # Make timestamps tz-aware (safe even if already correct)
        if _column_exists(bind, "business_integration_profiles", "created_at"):
            op.alter_column(
                "business_integration_profiles",
                "created_at",
                existing_type=postgresql.TIMESTAMP(),
                type_=sa.DateTime(timezone=True),
                existing_nullable=False,
            )
        if _column_exists(bind, "business_integration_profiles", "updated_at"):
            op.alter_column(
                "business_integration_profiles",
                "updated_at",
                existing_type=postgresql.TIMESTAMP(),
                type_=sa.DateTime(timezone=True),
                existing_nullable=False,
            )

        # Index scenario_id
        if not _index_exists(bind, "ix_business_integration_profiles_scenario_id"):
            op.create_index(
                "ix_business_integration_profiles_scenario_id",
                "business_integration_profiles",
                ["scenario_id"],
                unique=False,
            )

    # Index businesses.org_id
    if _table_exists(bind, "businesses"):
        if not _index_exists(bind, "ix_businesses_org_id"):
            op.create_index("ix_businesses_org_id", "businesses", ["org_id"], unique=False)

        # Replace FK to organizations with ON DELETE CASCADE if possible.
        # The autogen name may differ; handle the common one.
        fk_name = "businesses_org_id_fkey"
        if _constraint_exists(bind, fk_name):
            op.drop_constraint(fk_name, "businesses", type_="foreignkey")

        # Create a CASCADE FK if none exists for businesses.org_id -> organizations.id
        # We'll use a stable name to avoid "None" downgrades.
        cascade_fk_name = "fk_businesses_org_id_organizations"
        if not _constraint_exists(bind, cascade_fk_name):
            op.create_foreign_key(
                cascade_fk_name,
                "businesses",
                "organizations",
                ["org_id"],
                ["id"],
                ondelete="CASCADE",
            )


def downgrade() -> None:
    """Downgrade schema (best-effort; safe if partially applied)."""
    bind = op.get_bind()

    # Revert org FK (best effort)
    cascade_fk_name = "fk_businesses_org_id_organizations"
    if _constraint_exists(bind, cascade_fk_name):
        op.drop_constraint(cascade_fk_name, "businesses", type_="foreignkey")

    # Restore a non-cascade FK if it doesn't exist (use original name)
    original_fk = "businesses_org_id_fkey"
    if _table_exists(bind, "businesses") and not _constraint_exists(bind, original_fk):
        op.create_foreign_key(original_fk, "businesses", "organizations", ["org_id"], ["id"])

    if _index_exists(bind, "ix_businesses_org_id"):
        op.drop_index("ix_businesses_org_id", table_name="businesses")

    if _index_exists(bind, "ix_business_integration_profiles_scenario_id"):
        op.drop_index("ix_business_integration_profiles_scenario_id", table_name="business_integration_profiles")

    # Timestamp types back to naive (best effort)
    if _table_exists(bind, "business_integration_profiles"):
        if _column_exists(bind, "business_integration_profiles", "updated_at"):
            op.alter_column(
                "business_integration_profiles",
                "updated_at",
                existing_type=sa.DateTime(timezone=True),
                type_=postgresql.TIMESTAMP(),
                existing_nullable=False,
            )
        if _column_exists(bind, "business_integration_profiles", "created_at"):
            op.alter_column(
                "business_integration_profiles",
                "created_at",
                existing_type=sa.DateTime(timezone=True),
                type_=postgresql.TIMESTAMP(),
                existing_nullable=False,
            )

        if _column_exists(bind, "business_integration_profiles", "story_version"):
            op.drop_column("business_integration_profiles", "story_version")
        if _column_exists(bind, "business_integration_profiles", "scenario_id"):
            op.drop_column("business_integration_profiles", "scenario_id")

    if _constraint_exists(bind, "uq_business_category_id"):
        op.drop_constraint("uq_business_category_id", "business_category_map", type_="unique")

    # Recreate simulator tables only if missing (best effort)
    if not _table_exists(bind, "simulator_runs"):
        op.create_table(
            "simulator_runs",
            sa.Column("id", sa.VARCHAR(length=36), nullable=False),
            sa.Column("business_id", sa.VARCHAR(length=36), nullable=False),
            sa.Column("started_at", postgresql.TIMESTAMP(), nullable=False),
            sa.Column("params", postgresql.JSON(astext_type=sa.Text()), nullable=False),
            sa.ForeignKeyConstraint(
                ["business_id"],
                ["businesses.id"],
                name="simulator_runs_business_id_fkey",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name="simulator_runs_pkey"),
        )

    if not _table_exists(bind, "simulator_configs"):
        op.create_table(
            "simulator_configs",
            sa.Column("id", sa.VARCHAR(length=36), nullable=False),
            sa.Column("business_id", sa.VARCHAR(length=36), nullable=False),
            sa.Column("enabled", sa.BOOLEAN(), nullable=False),
            sa.Column("profile", sa.VARCHAR(length=40), nullable=False),
            sa.Column("avg_events_per_day", sa.INTEGER(), nullable=False),
            sa.Column("typical_ticket_cents", sa.INTEGER(), nullable=False),
            sa.Column("payroll_every_n_days", sa.INTEGER(), nullable=False),
            sa.Column("updated_at", postgresql.TIMESTAMP(), nullable=False),
            sa.ForeignKeyConstraint(
                ["business_id"],
                ["businesses.id"],
                name="simulator_configs_business_id_fkey",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name="simulator_configs_pkey"),
            sa.UniqueConstraint("business_id", name="simulator_configs_business_id_key"),
        )
