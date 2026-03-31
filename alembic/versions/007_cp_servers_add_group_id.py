"""cp_servers: add group_id for test grouping.

Revision ID: 007
Revises: 006
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cp_servers", sa.Column("group_id", sa.String(length=64), nullable=True))
    op.create_index("ix_cp_servers_group_id", "cp_servers", ["group_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cp_servers_group_id", table_name="cp_servers")
    op.drop_column("cp_servers", "group_id")
