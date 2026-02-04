"""add audit logs

Revision ID: 8b5c7d1b4f1a
Revises: 7c1b1d9c0a31, 97b7d2db67e0
Create Date: 2026-03-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b5c7d1b4f1a"
down_revision: Union[str, Sequence[str], None] = ("7c1b1d9c0a31", "97b7d2db67e0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("source_event_id", sa.String(length=120), nullable=True),
        sa.Column("rule_id", sa.String(length=36), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_business_id", "audit_logs", ["business_id"], unique=False)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)
    op.create_index("ix_audit_logs_rule_id", "audit_logs", ["rule_id"], unique=False)
    op.create_index("ix_audit_logs_source_event_id", "audit_logs", ["source_event_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_source_event_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_rule_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_business_id", table_name="audit_logs")
    op.drop_table("audit_logs")
