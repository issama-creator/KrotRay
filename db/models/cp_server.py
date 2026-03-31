"""VPN-узлы data plane: NL, мосты (control plane catalog)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class CpServer(Base):
    """
    Таблица cp_servers — соответствует спецификации servers (роли nl / standard_bridge / bypass_bridge).
    Отдельно от legacy `servers` (Xray gRPC для админки).
    """

    __tablename__ = "cp_servers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    short_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sni: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False, default="/")
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    current_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
