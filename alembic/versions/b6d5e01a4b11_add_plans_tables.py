"""add plans tables

Revision ID: b6d5e01a4b11
Revises: a9d7c2f0b1aa
Create Date: 2026-02-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b6d5e01a4b11"
down_revision = "a9d7c2f0b1aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("assigned_to_user_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_action_id", sa.String(length=36), nullable=True),
        sa.Column("primary_signal_id", sa.String(length=120), nullable=True),
        sa.Column("idempotency_key", sa.String(length=220), nullable=True),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_action_id"], ["action_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plans_business_created", "plans", ["business_id", "created_at"], unique=False)
    op.create_index("ix_plans_business_status", "plans", ["business_id", "status"], unique=False)
    op.create_index("ix_plans_source_action_id", "plans", ["source_action_id"], unique=False)

    op.create_table(
        "plan_conditions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("signal_id", sa.String(length=120), nullable=True),
        sa.Column("metric_key", sa.String(length=120), nullable=True),
        sa.Column("baseline_window_days", sa.Integer(), nullable=False),
        sa.Column("evaluation_window_days", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_conditions_plan_id", "plan_conditions", ["plan_id"], unique=False)

    op.create_table(
        "plan_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluation_start", sa.Date(), nullable=False),
        sa.Column("evaluation_end", sa.Date(), nullable=False),
        sa.Column("signal_state", sa.String(length=32), nullable=True),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("metric_baseline", sa.Float(), nullable=True),
        sa.Column("metric_delta", sa.Float(), nullable=True),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_observations_observed_at", "plan_observations", ["observed_at"], unique=False)
    op.create_index("ix_plan_observations_plan_id", "plan_observations", ["plan_id"], unique=False)

    op.create_table(
        "plan_state_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_state_events_actor_user_id", "plan_state_events", ["actor_user_id"], unique=False)
    op.create_index("ix_plan_state_events_plan_id", "plan_state_events", ["plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_plan_state_events_plan_id", table_name="plan_state_events")
    op.drop_index("ix_plan_state_events_actor_user_id", table_name="plan_state_events")
    op.drop_table("plan_state_events")

    op.drop_index("ix_plan_observations_plan_id", table_name="plan_observations")
    op.drop_index("ix_plan_observations_observed_at", table_name="plan_observations")
    op.drop_table("plan_observations")

    op.drop_index("ix_plan_conditions_plan_id", table_name="plan_conditions")
    op.drop_table("plan_conditions")

    op.drop_index("ix_plans_source_action_id", table_name="plans")
    op.drop_index("ix_plans_business_status", table_name="plans")
    op.drop_index("ix_plans_business_created", table_name="plans")
    op.drop_table("plans")
