"""Add edge_devices(last_seen, server_id) index for online-window aggregation.

Revision ID: 013
Revises: 012
"""

from typing import Sequence, Union

from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_edge_devices_last_seen_server_id",
        "edge_devices",
        ["last_seen", "server_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_edge_devices_last_seen_server_id", table_name="edge_devices")

