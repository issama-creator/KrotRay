from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Server(Base):
    """Сервер Xray + опционально строка в каталоге key-factory (Redis runtime)."""

    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    grpc_port: Mapped[int] = mapped_column(Integer, nullable=False)
    active_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Шаблон VLESS-ссылки для этого сервера (плейсхолдер {uuid}). Если пусто — используется глобальный VLESS_URL_TEMPLATE.
    vless_url_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # --- Каталог балансировщика (Postgres = источник правды; Redis заполняется scripts/init_redis_servers.py) ---
    kf_type: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment="wifi | bypass — участие в key-factory; NULL = только legacy Xray, не в Redis-каталоге",
    )
    region: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="eu | ru | произвольная метка")
    linked_server_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("servers.id", ondelete="SET NULL"),
        nullable=True,
        comment="Для bypass: ссылка на парный EU wifi-сервер (учёт в БД; балансировка по-прежнему по Redis)",
    )
    plan: Mapped[str] = mapped_column(String(64), nullable=False, server_default="default")

    subscriptions = relationship("Subscription", back_populates="server")
