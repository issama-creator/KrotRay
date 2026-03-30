"""Control plane: аккаунт пользователя (nullable telegram до привязки в боте)."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class CpUser(Base):
    """Таблица cp_users — соответствует спецификации users (telegram опционален)."""

    __tablename__ = "cp_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Подписка уровня аккаунта (оплата в Telegram-боте); устройство может получить max(device, account)
    account_subscription_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    devices = relationship("Device", back_populates="user")
