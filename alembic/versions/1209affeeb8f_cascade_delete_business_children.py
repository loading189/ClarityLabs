"""cascade delete business children

Revision ID: 1209affeeb8f
Revises: 26c3518eefab
Create Date: 2026-01-25 16:30:53.023073

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1209affeeb8f'
down_revision: Union[str, Sequence[str], None] = '26c3518eefab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- accounts.business_id -> businesses.id (CASCADE) ---
    op.drop_constraint("accounts_business_id_fkey", "accounts", type_="foreignkey")
    op.create_foreign_key(
        "accounts_business_id_fkey",
        "accounts",
        "businesses",
        ["business_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- raw_events.business_id -> businesses.id (CASCADE) ---
    op.drop_constraint("raw_events_business_id_fkey", "raw_events", type_="foreignkey")
    op.create_foreign_key(
        "raw_events_business_id_fkey",
        "raw_events",
        "businesses",
        ["business_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- categories.business_id -> businesses.id (CASCADE) ---
    # (you already have this in models; ensure DB matches)
    op.drop_constraint("categories_business_id_fkey", "categories", type_="foreignkey")
    op.create_foreign_key(
        "categories_business_id_fkey",
        "categories",
        "businesses",
        ["business_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- category_rules.business_id -> businesses.id (CASCADE) ---
    op.drop_constraint("category_rules_business_id_fkey", "category_rules", type_="foreignkey")
    op.create_foreign_key(
        "category_rules_business_id_fkey",
        "category_rules",
        "businesses",
        ["business_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- txn_categorizations.business_id -> businesses.id (CASCADE) ---
    op.drop_constraint("txn_categorizations_business_id_fkey", "txn_categorizations", type_="foreignkey")
    op.create_foreign_key(
        "txn_categorizations_business_id_fkey",
        "txn_categorizations",
        "businesses",
        ["business_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- business_category_map.business_id -> businesses.id (CASCADE) ---
    op.drop_constraint("business_category_map_business_id_fkey", "business_category_map", type_="foreignkey")
    op.create_foreign_key(
        "business_category_map_business_id_fkey",
        "business_category_map",
        "businesses",
        ["business_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- business_integration_profiles.business_id -> businesses.id (CASCADE) ---
    op.drop_constraint(
        "business_integration_profiles_business_id_fkey",
        "business_integration_profiles",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "business_integration_profiles_business_id_fkey",
        "business_integration_profiles",
        "businesses",
        ["business_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- businesses.org_id -> organizations.id (CASCADE) (optional but consistent) ---
    # If you want deleting an org to delete its businesses:
    # op.drop_constraint("businesses_org_id_fkey", "businesses", type_="foreignkey")
    # op.create_foreign_key(
    #     "businesses_org_id_fkey",
    #     "businesses",
    #     "organizations",
    #     ["org_id"],
    #     ["id"],
    #     ondelete="CASCADE",
    # )


def downgrade() -> None:
    # revert to NO ACTION / RESTRICT semantics (default)

    op.drop_constraint("accounts_business_id_fkey", "accounts", type_="foreignkey")
    op.create_foreign_key(
        "accounts_business_id_fkey",
        "accounts",
        "businesses",
        ["business_id"],
        ["id"],
    )

    op.drop_constraint("raw_events_business_id_fkey", "raw_events", type_="foreignkey")
    op.create_foreign_key(
        "raw_events_business_id_fkey",
        "raw_events",
        "businesses",
        ["business_id"],
        ["id"],
    )

    op.drop_constraint("categories_business_id_fkey", "categories", type_="foreignkey")
    op.create_foreign_key(
        "categories_business_id_fkey",
        "categories",
        "businesses",
        ["business_id"],
        ["id"],
    )

    op.drop_constraint("category_rules_business_id_fkey", "category_rules", type_="foreignkey")
    op.create_foreign_key(
        "category_rules_business_id_fkey",
        "category_rules",
        "businesses",
        ["business_id"],
        ["id"],
    )

    op.drop_constraint("txn_categorizations_business_id_fkey", "txn_categorizations", type_="foreignkey")
    op.create_foreign_key(
        "txn_categorizations_business_id_fkey",
        "txn_categorizations",
        "businesses",
        ["business_id"],
        ["id"],
    )

    op.drop_constraint("business_category_map_business_id_fkey", "business_category_map", type_="foreignkey")
    op.create_foreign_key(
        "business_category_map_business_id_fkey",
        "business_category_map",
        "businesses",
        ["business_id"],
        ["id"],
    )

    op.drop_constraint(
        "business_integration_profiles_business_id_fkey",
        "business_integration_profiles",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "business_integration_profiles_business_id_fkey",
        "business_integration_profiles",
        "businesses",
        ["business_id"],
        ["id"],
    )