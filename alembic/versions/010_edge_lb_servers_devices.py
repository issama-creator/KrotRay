"""Таблицы edge_servers / edge_devices — heartbeat по exit и выбор пар bridge+exit.

Revision ID: 010
Revises: 009

Не трогаем legacy `servers` и CP `devices`: отдельные таблицы под новое ядро.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "edge_servers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("group_id", sa.String(length=64), nullable=True),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("real_ip", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_edge_servers_type", "edge_servers", ["type"], unique=False)
    op.create_index("ix_edge_servers_group_id", "edge_servers", ["group_id"], unique=False)
    op.create_index("ix_edge_servers_is_active", "edge_servers", ["is_active"], unique=False)

    op.create_table(
        "edge_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("server_id", sa.Integer(), nullable=False),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["server_id"], ["edge_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", name="uq_edge_devices_device_id"),
    )
    op.create_index("ix_edge_devices_server_id", "edge_devices", ["server_id"], unique=False)
    op.create_index("ix_edge_devices_last_seen", "edge_devices", ["last_seen"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_edge_devices_last_seen", table_name="edge_devices")
    op.drop_index("ix_edge_devices_server_id", table_name="edge_devices")
    op.drop_table("edge_devices")
    op.drop_index("ix_edge_servers_is_active", table_name="edge_servers")
    op.drop_index("ix_edge_servers_group_id", table_name="edge_servers")
    op.drop_index("ix_edge_servers_type", table_name="edge_servers")
    op.drop_table("edge_servers")
