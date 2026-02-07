"""merge heads (plaid connection fields + raw event lifecycle)

Revision ID: f8697f10a343
Revises: 1b2a6f1a4f33, f4d83a9d1b2c
Create Date: 2026-02-04 12:34:56.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f8697f10a343"
down_revision: Union[str, Sequence[str], None] = ("1b2a6f1a4f33", "f4d83a9d1b2c")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
