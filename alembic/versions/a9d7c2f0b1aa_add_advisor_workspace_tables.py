"""add advisor workspace tables

Revision ID: a9d7c2f0b1aa
Revises: c2d9f4b1a7e3
Create Date: 2026-03-15 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9d7c2f0b1aa"
down_revision: Union[str, Sequence[str], None] = "c2d9f4b1a7e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "business_memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "user_id", name="uq_business_memberships_business_user"),
    )
    op.create_index("ix_business_memberships_business_id", "business_memberships", ["business_id"], unique=False)
    op.create_index("ix_business_memberships_user_id", "business_memberships", ["user_id"], unique=False)

    op.add_column("action_items", sa.Column("resolution_note", sa.Text(), nullable=True))
    op.add_column("action_items", sa.Column("resolution_meta_json", sa.JSON(), nullable=True))
    op.add_column("action_items", sa.Column("assigned_to_user_id", sa.String(length=36), nullable=True))
    op.add_column("action_items", sa.Column("resolved_by_user_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_action_items_assigned_to_user",
        "action_items",
        "users",
        ["assigned_to_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_action_items_resolved_by_user",
        "action_items",
        "users",
        ["resolved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_action_items_assigned_status",
        "action_items",
        ["assigned_to_user_id", "status"],
        unique=False,
    )

    op.create_table(
        "action_state_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=False),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["action_id"], ["action_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_action_state_events_action_id", "action_state_events", ["action_id"], unique=False)
    op.create_index("ix_action_state_events_actor_user_id", "action_state_events", ["actor_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_action_state_events_actor_user_id", table_name="action_state_events")
    op.drop_index("ix_action_state_events_action_id", table_name="action_state_events")
    op.drop_table("action_state_events")

    op.drop_index("ix_action_items_assigned_status", table_name="action_items")
    op.drop_constraint("fk_action_items_resolved_by_user", "action_items", type_="foreignkey")
    op.drop_constraint("fk_action_items_assigned_to_user", "action_items", type_="foreignkey")
    op.drop_column("action_items", "resolved_by_user_id")
    op.drop_column("action_items", "assigned_to_user_id")
    op.drop_column("action_items", "resolution_meta_json")
    op.drop_column("action_items", "resolution_note")

    op.drop_index("ix_business_memberships_user_id", table_name="business_memberships")
    op.drop_index("ix_business_memberships_business_id", table_name="business_memberships")
    op.drop_table("business_memberships")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
