"""add action items table

Revision ID: c2d9f4b1a7e3
Revises: f8697f10a343
Create Date: 2026-02-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c2d9f4b1a7e3"
down_revision = "f8697f10a343"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_signal_id", sa.String(length=120), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("rationale_json", sa.JSON(), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=220), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "idempotency_key", name="uq_action_items_business_idempotency"),
    )
    op.create_index("ix_action_items_business_priority", "action_items", ["business_id", "priority"], unique=False)
    op.create_index("ix_action_items_business_status", "action_items", ["business_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_action_items_business_status", table_name="action_items")
    op.drop_index("ix_action_items_business_priority", table_name="action_items")
    op.drop_table("action_items")
