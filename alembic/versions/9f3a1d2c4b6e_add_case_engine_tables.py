"""add case engine tables

Revision ID: 9f3a1d2c4b6e
Revises: b6d5e01a4b11
Create Date: 2026-02-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f3a1d2c4b6e"
down_revision = "b6d5e01a4b11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("domain", sa.String(length=40), nullable=False),
        sa.Column("primary_signal_type", sa.String(length=80), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="low"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("risk_score_snapshot", sa.JSON(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_to", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cases_business_status", "cases", ["business_id", "status"])
    op.create_index("ix_cases_business_severity", "cases", ["business_id", "severity"])
    op.create_index("ix_cases_domain_status", "cases", ["domain", "status"])
    op.create_index("ix_cases_opened_at", "cases", ["opened_at"])

    op.create_table(
        "case_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_events_case_id", "case_events", ["case_id"])
    op.create_index("ix_case_events_created_at", "case_events", ["created_at"])

    op.create_table(
        "case_signals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("business_id", sa.String(length=36), nullable=False),
        sa.Column("signal_id", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "signal_id", name="uq_case_signals_business_signal"),
    )
    op.create_index("ix_case_signals_case_id", "case_signals", ["case_id"])

    op.create_table(
        "case_ledger_anchors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("anchor_key", sa.String(length=140), nullable=False),
        sa.Column("anchor_payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "anchor_key", name="uq_case_ledger_anchor_key"),
    )
    op.create_index("ix_case_ledger_anchors_case_id", "case_ledger_anchors", ["case_id"])

    op.add_column("plans", sa.Column("case_id", sa.String(length=36), nullable=True))
    op.create_index("ix_plans_case_id", "plans", ["case_id"])
    op.create_foreign_key("fk_plans_case_id_cases", "plans", "cases", ["case_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_plans_case_id_cases", "plans", type_="foreignkey")
    op.drop_index("ix_plans_case_id", table_name="plans")
    op.drop_column("plans", "case_id")

    op.drop_index("ix_case_ledger_anchors_case_id", table_name="case_ledger_anchors")
    op.drop_table("case_ledger_anchors")

    op.drop_index("ix_case_signals_case_id", table_name="case_signals")
    op.drop_table("case_signals")

    op.drop_index("ix_case_events_created_at", table_name="case_events")
    op.drop_index("ix_case_events_case_id", table_name="case_events")
    op.drop_table("case_events")

    op.drop_index("ix_cases_opened_at", table_name="cases")
    op.drop_index("ix_cases_domain_status", table_name="cases")
    op.drop_index("ix_cases_business_severity", table_name="cases")
    op.drop_index("ix_cases_business_status", table_name="cases")
    op.drop_table("cases")
