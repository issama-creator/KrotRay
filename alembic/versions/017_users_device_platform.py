"""users: nullable telegram_id, platform + device_stable_id for native app trial.

Revision ID: 017
Revises: 016
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("platform", sa.String(16), nullable=True))
    op.add_column("users", sa.Column("device_stable_id", sa.String(128), nullable=True))
    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.BigInteger(),
        nullable=True,
        existing_nullable=False,
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_platform_device
        ON users (platform, device_stable_id)
        WHERE platform IS NOT NULL AND device_stable_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_users_platform_device")
    op.drop_column("users", "device_stable_id")
    op.drop_column("users", "platform")
    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.BigInteger(),
        nullable=False,
        existing_nullable=True,
    )
