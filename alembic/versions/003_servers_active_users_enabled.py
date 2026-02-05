"""Servers: active_users, max_users, enabled, created_at (Итерация 6.1)

Revision ID: 003
Revises: 002
Create Date: 2026-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("servers", sa.Column("active_users", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("servers", sa.Column("max_users", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("servers", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("servers", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.execute("UPDATE servers SET enabled = is_active")
    op.drop_column("servers", "is_active")


def downgrade() -> None:
    op.add_column("servers", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("UPDATE servers SET is_active = enabled WHERE True")
    op.drop_column("servers", "created_at")
    op.drop_column("servers", "enabled")
    op.drop_column("servers", "max_users")
    op.drop_column("servers", "active_users")
