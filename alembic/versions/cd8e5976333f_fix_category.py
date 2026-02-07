"""Fix category indexes + txn categorization uniqueness (idempotent).

Revision ID: cd8e5976333f
Revises: 620795993094
Create Date: 2026-01-25 12:33:16.374602
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "cd8e5976333f"
down_revision: Union[str, Sequence[str], None] = "620795993094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(bind, name: str) -> bool:
    return bind.execute(
        text(
            """
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'i'
              AND c.relname = :name
            """
        ),
        {"name": name},
    ).first() is not None


def _constraint_exists(bind, name: str) -> bool:
    return bind.execute(
        text(
            """
            SELECT 1
            FROM pg_constraint
            WHERE conname = :name
            """
        ),
        {"name": name},
    ).first() is not None


def upgrade() -> None:
    """Upgrade schema (safe to re-run)."""
    bind = op.get_bind()

    # accounts
    if not _index_exists(bind, "ix_accounts_business_id"):
        op.create_index("ix_accounts_business_id", "accounts", ["business_id"], unique=False)

    # business_category_map (some environments may already have one set of these indexes)
    for idx_name, cols in [
        ("ix_bcm_business_id", ["business_id"]),
        ("ix_bcm_category_id", ["category_id"]),
        ("ix_bcm_system_key", ["system_key"]),
        ("ix_business_category_map_business_id", ["business_id"]),
        ("ix_business_category_map_category_id", ["category_id"]),
        ("ix_business_category_map_system_key", ["system_key"]),
    ]:
        if not _index_exists(bind, idx_name):
            op.create_index(idx_name, "business_category_map", cols, unique=False)

    # categories
    for idx_name, cols in [
        ("ix_categories_account_id", ["account_id"]),
        ("ix_categories_business_id", ["business_id"]),
    ]:
        if not _index_exists(bind, idx_name):
            op.create_index(idx_name, "categories", cols, unique=False)

    # category_rules
    for idx_name, cols in [
        ("ix_category_rules_business_id", ["business_id"]),
        ("ix_category_rules_category_id", ["category_id"]),
    ]:
        if not _index_exists(bind, idx_name):
            op.create_index(idx_name, "category_rules", cols, unique=False)

    # raw_events
    if not _index_exists(bind, "ix_raw_events_business_id"):
        op.create_index("ix_raw_events_business_id", "raw_events", ["business_id"], unique=False)

    # txn_categorizations
    for idx_name, cols in [
        ("ix_txn_categorizations_business_id", ["business_id"]),
        ("ix_txn_categorizations_category_id", ["category_id"]),
        ("ix_txncat_business_id", ["business_id"]),
        ("ix_txncat_source_event_id", ["source_event_id"]),
    ]:
        if not _index_exists(bind, idx_name):
            op.create_index(idx_name, "txn_categorizations", cols, unique=False)

    if not _constraint_exists(bind, "uq_txncat_business_sourceevent"):
        op.create_unique_constraint(
            "uq_txncat_business_sourceevent",
            "txn_categorizations",
            ["business_id", "source_event_id"],
        )


def downgrade() -> None:
    """Downgrade schema (best-effort; safe if already removed)."""
    bind = op.get_bind()

    if _constraint_exists(bind, "uq_txncat_business_sourceevent"):
        op.drop_constraint("uq_txncat_business_sourceevent", "txn_categorizations", type_="unique")

    for idx_name, table in [
        ("ix_txncat_source_event_id", "txn_categorizations"),
        ("ix_txncat_business_id", "txn_categorizations"),
        ("ix_txn_categorizations_category_id", "txn_categorizations"),
        ("ix_txn_categorizations_business_id", "txn_categorizations"),
        ("ix_raw_events_business_id", "raw_events"),
        ("ix_category_rules_category_id", "category_rules"),
        ("ix_category_rules_business_id", "category_rules"),
        ("ix_categories_business_id", "categories"),
        ("ix_categories_account_id", "categories"),
        ("ix_business_category_map_system_key", "business_category_map"),
        ("ix_business_category_map_category_id", "business_category_map"),
        ("ix_business_category_map_business_id", "business_category_map"),
        ("ix_bcm_system_key", "business_category_map"),
        ("ix_bcm_category_id", "business_category_map"),
        ("ix_bcm_business_id", "business_category_map"),
        ("ix_accounts_business_id", "accounts"),
    ]:
        if _index_exists(bind, idx_name):
            op.drop_index(idx_name, table_name=table)
