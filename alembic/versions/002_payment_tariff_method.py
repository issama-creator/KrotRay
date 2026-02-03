"""Payment: tariff_months, payment_method (Итерация 5)

Revision ID: 002
Revises: 001
Create Date: 2025-02-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("tariff_months", sa.Integer(), nullable=True))
    op.add_column("payments", sa.Column("payment_method", sa.String(16), nullable=True))
    op.execute("UPDATE payments SET tariff_months = 1 WHERE tariff_months IS NULL")
    op.execute("UPDATE payments SET payment_method = 'card' WHERE payment_method IS NULL")
    op.alter_column("payments", "tariff_months", nullable=False, existing_type=sa.Integer())
    op.alter_column("payments", "payment_method", nullable=False, existing_type=sa.String(16))


def downgrade() -> None:
    op.drop_column("payments", "payment_method")
    op.drop_column("payments", "tariff_months")
