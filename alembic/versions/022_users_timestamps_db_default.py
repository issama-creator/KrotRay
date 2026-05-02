"""users: DEFAULT NOW() для created_at и updated_at в Postgres.

Страховка, если ORM не передал метки времени в INSERT: колонки NOT NULL без DEFAULT давали 500.

Revision ID: 022
Revises: 021
"""

from typing import Sequence, Union

from alembic import op


revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN created_at SET DEFAULT NOW()")
    op.execute("ALTER TABLE users ALTER COLUMN updated_at SET DEFAULT NOW()")


def downgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN created_at DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN updated_at DROP DEFAULT")
