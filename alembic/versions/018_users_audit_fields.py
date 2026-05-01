"""users: updated_at, telegram_linked_at для аудита и просмотра в админке.

Revision ID: 018
Revises: 017
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("telegram_linked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET updated_at = COALESCE(created_at, NOW()) WHERE updated_at IS NULL")
    op.alter_column(
        "users",
        "updated_at",
        nullable=False,
        server_default=sa.func.now(),
        existing_type=sa.DateTime(timezone=True),
    )


def downgrade() -> None:
    op.drop_column("users", "telegram_linked_at")
    op.drop_column("users", "updated_at")
