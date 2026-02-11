"""Subscription: device limit fields (allowed_devices, disabled_by_limit, violation_count)

Revision ID: 005
Revises: 004
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("allowed_devices", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("subscriptions", sa.Column("disabled_by_limit", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("subscriptions", sa.Column("violation_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("subscriptions", "violation_count")
    op.drop_column("subscriptions", "disabled_by_limit")
    op.drop_column("subscriptions", "allowed_devices")
