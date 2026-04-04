"""Устройство клиента: один device_id = одно устройство."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # UUID строкой — совместимо с SQLite и PostgreSQL
    device_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("cp_users.id", ondelete="CASCADE"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)  # android | ios
    subscription_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")  # standard | bypass
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Пинг из Flutter, пока пользователь считает VPN включённым (не число TCP-сессий на ноде).
    tunnel_last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Последние узлы из успешного GET /config?device_id=… (для подсчёта «активных» по heartbeat).
    last_bridge_server_id: Mapped[int | None] = mapped_column(
        ForeignKey("cp_servers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    last_nl_server_id: Mapped[int | None] = mapped_column(
        ForeignKey("cp_servers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    user = relationship("CpUser", back_populates="devices")
