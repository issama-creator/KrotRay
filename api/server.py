"""Выбор сервера для новой подписки (Итерация 6.1)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Server


def get_least_loaded_server(db: Session) -> Server | None:
    """
    Возвращает наименее загруженный включённый сервер.
    ORDER BY active_users ASC, чтобы брать сервер с минимумом пользователей.
    """
    row = db.execute(
        select(Server)
        .where(Server.enabled.is_(True))
        .where(Server.active_users < Server.max_users)
        .order_by(Server.active_users.asc())
        .limit(1)
    )
    return row.scalars().first()
