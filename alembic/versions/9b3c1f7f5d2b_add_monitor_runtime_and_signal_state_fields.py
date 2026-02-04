"""add monitor runtime and signal state fields

Revision ID: 9b3c1f7f5d2b
Revises: e1feb5472f06
Create Date: 2025-02-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9b3c1f7f5d2b"
down_revision = "e1feb5472f06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("health_signal_states") as batch_op:
        batch_op.add_column(sa.Column("signal_type", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("fingerprint", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("severity", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("title", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("payload_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("detected_at", sa.DateTime(), nullable=True))

    op.create_table(
        "monitor_runtime",
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("last_pulse_at", sa.DateTime(), nullable=True),
        sa.Column("newest_event_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("business_id"),
    )
    op.create_index("ix_monitor_runtime_business_id", "monitor_runtime", ["business_id"])


def downgrade() -> None:
    op.drop_index("ix_monitor_runtime_business_id", table_name="monitor_runtime")
    op.drop_table("monitor_runtime")

    with op.batch_alter_table("health_signal_states") as batch_op:
        batch_op.drop_column("detected_at")
        batch_op.drop_column("payload_json")
        batch_op.drop_column("summary")
        batch_op.drop_column("title")
        batch_op.drop_column("severity")
        batch_op.drop_column("fingerprint")
        batch_op.drop_column("signal_type")
