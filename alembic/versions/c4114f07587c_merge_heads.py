"""restore missing revision c4114f07587c (no-op)

This revision exists in the database (alembic_version), but the migration file
was missing from the repo. We restore it as a no-op so Alembic can build the
revision graph again.

Revision ID: c4114f07587c
Revises: 3b7f9b12e4c7
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4114f07587c"
down_revision: Union[str, Sequence[str], None] = "3b7f9b12e4c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # no-op: this migration only restores the missing revision file
    pass


def downgrade() -> None:
    # no-op
    pass
