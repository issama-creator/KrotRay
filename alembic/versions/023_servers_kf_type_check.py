"""servers: CHECK kf_type IN (wifi, bypass) или NULL.

Revision ID: 023
Revises: 022
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = :n",
        ),
        {"n": "ck_servers_kf_type_wifi_bypass"},
    ).scalar()
    if exists:
        return
    op.execute(
        """
        ALTER TABLE servers ADD CONSTRAINT ck_servers_kf_type_wifi_bypass
        CHECK (kf_type IS NULL OR kf_type IN ('wifi', 'bypass'))
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_servers_kf_type_wifi_bypass", "servers", type_="check")
