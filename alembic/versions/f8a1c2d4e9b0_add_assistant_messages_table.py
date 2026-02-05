"""add assistant messages table

Revision ID: f8a1c2d4e9b0
Revises: 9b3c1f7f5d2b
Create Date: 2026-02-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f8a1c2d4e9b0"
down_revision = "9b3c1f7f5d2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("author", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("signal_id", sa.String(length=120), nullable=True),
        sa.Column("audit_id", sa.String(length=36), nullable=True),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_messages_business_created", "assistant_messages", ["business_id", "created_at", "id"], unique=False)
    op.create_index(op.f("ix_assistant_messages_business_id"), "assistant_messages", ["business_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_assistant_messages_business_id"), table_name="assistant_messages")
    op.drop_index("ix_assistant_messages_business_created", table_name="assistant_messages")
    op.drop_table("assistant_messages")
