"""add work items table

Revision ID: 6f8a2c1d9b44
Revises: 2d7d9f61c2aa
Create Date: 2026-02-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6f8a2c1d9b44"
down_revision = "2d7d9f61c2aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=220), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_work_items_idempotency_key"),
    )
    op.create_index("ix_work_items_business_status_priority_due", "work_items", ["business_id", "status", "priority", "due_at"], unique=False)
    op.create_index("ix_work_items_case_id", "work_items", ["case_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_work_items_case_id", table_name="work_items")
    op.drop_index("ix_work_items_business_status_priority_due", table_name="work_items")
    op.drop_table("work_items")
