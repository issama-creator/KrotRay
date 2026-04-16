"""Add pool column to edge_servers for split balancing.

Revision ID: 012
Revises: 011
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "edge_servers",
        sa.Column("pool", sa.String(length=32), nullable=False, server_default="shared"),
    )
    op.create_index("ix_edge_servers_pool", "edge_servers", ["pool"], unique=False)
    op.create_index("ix_edge_servers_type_pool", "edge_servers", ["type", "pool"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_edge_servers_type_pool", table_name="edge_servers")
    op.drop_index("ix_edge_servers_pool", table_name="edge_servers")
    op.drop_column("edge_servers", "pool")

