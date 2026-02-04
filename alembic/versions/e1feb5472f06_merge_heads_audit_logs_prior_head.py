"""merge heads (audit logs + prior head)

Revision ID: e1feb5472f06
Revises: c4114f07587c, 8b5c7d1b4f1a
Create Date: 2026-02-04 11:54:51.433846

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1feb5472f06'
down_revision: Union[str, Sequence[str], None] = ('c4114f07587c', '8b5c7d1b4f1a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
