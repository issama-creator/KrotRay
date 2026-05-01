from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class AccessKey(Base):
    """Ключ доступа для нативного клиента после оплаты в Telegram (без telegram_id в приложении)."""

    __tablename__ = "access_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    devices = relationship("AccessKeyDevice", back_populates="access_key", cascade="all, delete-orphan")


class AccessKeyDevice(Base):
    """Устройства, привязанные к одному access key (лимит N)."""

    __tablename__ = "access_key_devices"
    __table_args__ = (
        UniqueConstraint("access_key_id", "platform", "device_stable_id", name="uq_access_key_device_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    access_key_id: Mapped[int] = mapped_column(ForeignKey("access_keys.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    device_stable_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    access_key = relationship("AccessKey", back_populates="devices")
