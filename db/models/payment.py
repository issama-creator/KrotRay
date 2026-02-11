from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func  # noqa: I001
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="RUB")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending, completed, failed, canceled
    tariff_months: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 3, or 6
    payment_method: Mapped[str] = mapped_column(String(16), nullable=False)  # card | sbp
    devices: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # количество устройств (1-5)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)  # ID в ЮKassa (yookassa_payment_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="payments")
