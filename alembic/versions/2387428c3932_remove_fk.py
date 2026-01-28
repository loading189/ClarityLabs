"""remove fk

Revision ID: 2387428c3932
Revises: cd8e5976333f
Create Date: 2026-01-25 12:40:43.408307

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2387428c3932'
down_revision: Union[str, Sequence[str], None] = 'cd8e5976333f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # drop FK constraint if it exists
    op.drop_constraint(
        "business_category_map_system_key_fkey",
        "business_category_map",
        type_="foreignkey",
    )


def downgrade():
    # restore FK constraint
    op.create_foreign_key(
        "business_category_map_system_key_fkey",
        "business_category_map",
        "system_categories",
        ["system_key"],
        ["key"],
        ondelete="CASCADE",
    )
