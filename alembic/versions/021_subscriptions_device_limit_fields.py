"""subscriptions: allowed_devices, disabled_by_limit, violation_count (лимит устройств).

ORM и платежи уже ожидают эти колонки; без них любой SELECT по subscriptions даёт 500.

Revision ID: 021
Revises: 020
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Колонки могли быть добавлены вручную до этой ревизии — не дублируем."""
    conn = op.get_bind()
    existing = {c["name"] for c in inspect(conn).get_columns("subscriptions")}
    if "allowed_devices" not in existing:
        op.add_column(
            "subscriptions",
            sa.Column("allowed_devices", sa.Integer(), nullable=False, server_default="1"),
        )
    if "disabled_by_limit" not in existing:
        op.add_column(
            "subscriptions",
            sa.Column("disabled_by_limit", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "violation_count" not in existing:
        op.add_column(
            "subscriptions",
            sa.Column("violation_count", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing = {c["name"] for c in inspect(conn).get_columns("subscriptions")}
    for name in ("violation_count", "disabled_by_limit", "allowed_devices"):
        if name in existing:
            op.drop_column("subscriptions", name)
