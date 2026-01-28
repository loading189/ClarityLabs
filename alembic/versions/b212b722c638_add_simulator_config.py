"""add simulator config

Revision ID: b212b722c638
Revises: d6e303265d55
Create Date: 2026-01-19 08:47:50.118579

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b212b722c638'
down_revision: Union[str, Sequence[str], None] = 'd6e303265d55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("businesses", sa.Column("sim_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("businesses", sa.Column("sim_profile", sa.String(length=40), nullable=False, server_default=sa.text("'normal'")))

def downgrade():
    op.drop_column("businesses", "sim_profile")
    op.drop_column("businesses", "sim_enabled")
