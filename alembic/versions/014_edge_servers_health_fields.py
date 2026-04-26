"""Add health-check fields for edge_servers.

Revision ID: 014
Revises: 013
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("edge_servers", sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("edge_servers", sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "edge_servers",
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "edge_servers",
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("edge_servers", sa.Column("last_error", sa.Text(), nullable=True))

    op.create_index("ix_edge_servers_last_check_at", "edge_servers", ["last_check_at"], unique=False)
    op.create_index("ix_edge_servers_fail_count", "edge_servers", ["fail_count"], unique=False)
    op.create_index("ix_edge_servers_success_count", "edge_servers", ["success_count"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_edge_servers_success_count", table_name="edge_servers")
    op.drop_index("ix_edge_servers_fail_count", table_name="edge_servers")
    op.drop_index("ix_edge_servers_last_check_at", table_name="edge_servers")
    op.drop_column("edge_servers", "last_error")
    op.drop_column("edge_servers", "success_count")
    op.drop_column("edge_servers", "fail_count")
    op.drop_column("edge_servers", "last_ok_at")
    op.drop_column("edge_servers", "last_check_at")

