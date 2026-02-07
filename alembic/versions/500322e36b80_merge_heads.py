"""merge heads

Revision ID: 500322e36b80
Revises: 3b7f9b12e4c7, 9d7e4d8b2f5a
Create Date: 2026-02-06 19:49:55.165432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '500322e36b80'
down_revision: Union[str, Sequence[str], None] = ('3b7f9b12e4c7', '9d7e4d8b2f5a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
