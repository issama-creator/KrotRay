"""Control plane: cp_users, devices, cp_servers (VPN data plane catalog).

Revision ID: 005
Revises: 004
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cp_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("account_subscription_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cp_users_telegram_id", "cp_users", ["telegram_id"], unique=False)

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("subscription_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan_type", sa.String(32), nullable=False, server_default="standard"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["cp_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_devices_device_id", "devices", ["device_id"], unique=True)
    op.create_index("ix_devices_user_id", "devices", ["user_id"], unique=False)

    op.create_table(
        "cp_servers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ip", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("short_id", sa.String(64), nullable=False),
        sa.Column("sni", sa.String(255), nullable=False),
        sa.Column("path", sa.String(255), nullable=False, server_default="/"),
        sa.Column("max_users", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_users_base", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("current_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cp_servers_role", "cp_servers", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cp_servers_role", table_name="cp_servers")
    op.drop_table("cp_servers")
    op.drop_index("ix_devices_user_id", table_name="devices")
    op.drop_index("ix_devices_device_id", table_name="devices")
    op.drop_table("devices")
    op.drop_index("uq_cp_users_telegram_id_not_null", table_name="cp_users")
    op.drop_index("ix_cp_users_telegram_id", table_name="cp_users")
    op.drop_table("cp_users")
