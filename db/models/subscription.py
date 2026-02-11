from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")  # active, expired, disabled
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tariff_months: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 3, or 6
    uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Xray UUID, заполняется в итерации 6
    server_id: Mapped[int | None] = mapped_column(ForeignKey("servers.id", ondelete="SET NULL"), nullable=True)
    allowed_devices: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # Лимит устройств
    disabled_by_limit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # Отключен из-за превышения лимита
    violation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Счетчик нарушений
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="subscriptions")
    server = relationship("Server", back_populates="subscriptions")
