"""subscriptions: allowed_devices, disabled_by_limit, violation_count (лимит устройств).

ORM и платежи уже ожидают эти колонки; без них любой SELECT по subscriptions даёт 500.

Revision ID: 021
Revises: 020
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("allowed_devices", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("disabled_by_limit", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "subscriptions",
        sa.Column("violation_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "violation_count")
    op.drop_column("subscriptions", "disabled_by_limit")
    op.drop_column("subscriptions", "allowed_devices")
