from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class EdgeSession(Base):
    __tablename__ = "edge_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    key: Mapped[str] = mapped_column(String(64), ForeignKey("edge_users.key", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    server_id: Mapped[int] = mapped_column(Integer, ForeignKey("edge_servers.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

