"""Edge sessions table for event-based connect/disconnect with TTL.

Revision ID: 015
Revises: 014
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "edge_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("server_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["key"], ["edge_users.key"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["server_id"], ["edge_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_edge_sessions_session_id"),
    )

    op.create_index("ix_edge_sessions_server_expires", "edge_sessions", ["server_id", "expires_at"], unique=False)
    op.create_index("ix_edge_sessions_key_expires", "edge_sessions", ["key", "expires_at"], unique=False)
    op.create_index("ix_edge_sessions_expires_at", "edge_sessions", ["expires_at"], unique=False)
    op.create_index("ix_edge_sessions_stopped_at", "edge_sessions", ["stopped_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_edge_sessions_stopped_at", table_name="edge_sessions")
    op.drop_index("ix_edge_sessions_expires_at", table_name="edge_sessions")
    op.drop_index("ix_edge_sessions_key_expires", table_name="edge_sessions")
    op.drop_index("ix_edge_sessions_server_expires", table_name="edge_sessions")
    op.drop_table("edge_sessions")

