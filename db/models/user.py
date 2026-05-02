from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """Пользователь: Mini App (telegram), нативное приложение (platform+device), общий доступ key-factory."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="PK, совпадает с account_id в API")

    telegram_id: Mapped[int | None] = mapped_column(
        BigInteger,
        unique=True,
        nullable=True,
        index=True,
        comment="Telegram user id; NULL пока только стор без привязки",
    )
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Из Telegram профиля")
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Из Telegram профиля")

    platform: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="android | ios для стора")
    device_stable_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Стабильный id устройства (ANDROID_ID / аналог); уникально вместе с platform",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utc_now,
        comment="Регистрация строки; начало окна триала key-factory",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        default=_utc_now,
        comment="Последнее изменение записи",
    )
    telegram_linked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Когда впервые привязан telegram_id (Mini App или POST /attach)",
    )

    subscription_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Платная подписка до этой даты; webhook ЮKassa продлевает",
    )

    subscriptions = relationship("Subscription", back_populates="user")
    payments = relationship("Payment", back_populates="user")
