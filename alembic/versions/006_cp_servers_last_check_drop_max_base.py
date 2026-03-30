"""cp_servers: last_check; убрать max_users_base (фиксированный max_users).

Revision ID: 006
Revises: 005
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cp_servers",
        sa.Column("last_check", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_column("cp_servers", "max_users_base")


def downgrade() -> None:
    op.add_column(
        "cp_servers",
        sa.Column("max_users_base", sa.Integer(), nullable=False, server_default="100"),
    )
    op.drop_column("cp_servers", "last_check")
