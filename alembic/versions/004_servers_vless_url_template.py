"""Servers: vless_url_template для нескольких серверов (10–30)

Revision ID: 004
Revises: 003
Create Date: 2026-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("servers", sa.Column("vless_url_template", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("servers", "vless_url_template")
