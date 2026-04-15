"""Edge users table for key-based config/ping auth.

Revision ID: 011
Revises: 010
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "edge_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", name="uq_edge_users_device_id"),
        sa.UniqueConstraint("key", name="uq_edge_users_key"),
    )
    op.create_index("ix_edge_users_key", "edge_users", ["key"], unique=False)
    op.create_index("ix_edge_users_device_id", "edge_users", ["device_id"], unique=False)
    op.create_index("ix_edge_users_expires_at", "edge_users", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_edge_users_expires_at", table_name="edge_users")
    op.drop_index("ix_edge_users_device_id", table_name="edge_users")
    op.drop_index("ix_edge_users_key", table_name="edge_users")
    op.drop_table("edge_users")
