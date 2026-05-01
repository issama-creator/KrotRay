"""access_keys + access_key_devices для доступа нативного клиента по ключу после оплаты.

Revision ID: 019
Revises: 018
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_access_keys_token", "access_keys", ["token"], unique=True)
    op.create_index("ix_access_keys_user_id", "access_keys", ["user_id"])

    op.create_table(
        "access_key_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("access_key_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("device_stable_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["access_key_id"], ["access_keys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("access_key_id", "platform", "device_stable_id", name="uq_access_key_device_pair"),
    )
    op.create_index("ix_access_key_devices_access_key_id", "access_key_devices", ["access_key_id"])


def downgrade() -> None:
    op.drop_index("ix_access_key_devices_access_key_id", table_name="access_key_devices")
    op.drop_table("access_key_devices")
    op.drop_index("ix_access_keys_user_id", table_name="access_keys")
    op.drop_index("ix_access_keys_token", table_name="access_keys")
    op.drop_table("access_keys")
