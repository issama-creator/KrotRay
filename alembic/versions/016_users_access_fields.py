"""Add minimal access fields to users.

Revision ID: 016
Revises: 015
Create Date: 2026-05-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET created_at = NOW() WHERE created_at IS NULL")
    op.alter_column("users", "created_at", nullable=False, existing_type=sa.DateTime(timezone=True))


def downgrade() -> None:
    op.drop_column("users", "subscription_expires_at")
    op.drop_column("users", "created_at")
