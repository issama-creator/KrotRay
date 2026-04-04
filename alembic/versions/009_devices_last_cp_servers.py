"""devices: last assigned bridge/nl from /config (для баланса по vpn-heartbeat).

Revision ID: 009
Revises: 008
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("last_bridge_server_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("last_nl_server_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_devices_last_bridge_server_id",
        "devices",
        "cp_servers",
        ["last_bridge_server_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_devices_last_nl_server_id",
        "devices",
        "cp_servers",
        ["last_nl_server_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_devices_last_bridge_server_id",
        "devices",
        ["last_bridge_server_id"],
        unique=False,
    )
    op.create_index(
        "ix_devices_last_nl_server_id",
        "devices",
        ["last_nl_server_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_devices_last_nl_server_id", table_name="devices")
    op.drop_index("ix_devices_last_bridge_server_id", table_name="devices")
    op.drop_constraint("fk_devices_last_nl_server_id", "devices", type_="foreignkey")
    op.drop_constraint("fk_devices_last_bridge_server_id", "devices", type_="foreignkey")
    op.drop_column("devices", "last_nl_server_id")
    op.drop_column("devices", "last_bridge_server_id")
