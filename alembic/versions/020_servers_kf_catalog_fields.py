"""servers: поля каталога key-factory (wifi/bypass, регион, связка RU→EU, план).

Revision ID: 020
Revises: 019
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("servers", sa.Column("kf_type", sa.String(length=16), nullable=True))
    op.add_column("servers", sa.Column("region", sa.String(length=32), nullable=True))
    op.add_column("servers", sa.Column("linked_server_id", sa.Integer(), nullable=True))
    op.add_column(
        "servers",
        sa.Column("plan", sa.String(length=64), nullable=False, server_default="default"),
    )
    op.create_foreign_key(
        "fk_servers_linked_server_id",
        "servers",
        "servers",
        ["linked_server_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_servers_kf_type", "servers", ["kf_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_servers_kf_type", table_name="servers")
    op.drop_constraint("fk_servers_linked_server_id", "servers", type_="foreignkey")
    op.drop_column("servers", "plan")
    op.drop_column("servers", "linked_server_id")
    op.drop_column("servers", "region")
    op.drop_column("servers", "kf_type")
