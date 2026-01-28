"""cascade delete business children

Revision ID: 26c3518eefab
Revises: 2387428c3932
Create Date: 2026-01-25 15:25:55.692543

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '26c3518eefab'
down_revision: Union[str, Sequence[str], None] = '2387428c3932'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
