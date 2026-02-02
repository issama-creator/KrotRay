"""Проверка Telegram initData и получение пользователя."""
import hashlib
import hmac
import json
from typing import Any
from urllib.parse import parse_qsl

from sqlalchemy import select
from sqlalchemy.orm import Session

from bot.config import BOT_TOKEN
from db.models import User


def verify_init_data(init_data: str) -> dict[str, Any] | None:
    """
    Проверяет подпись initData от Telegram WebApp.
    Возвращает распарсенные данные или None при ошибке.
    """
    if not init_data or not BOT_TOKEN:
        return None

    try:
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )
        # По документации Telegram: HMAC-SHA256(key=WebAppData, message=token)
        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256,
        ).digest()
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        auth_date = int(parsed.get("auth_date", 0))
        if auth_date < 0:
            return None
        # Проверка срока действия (24 часа)
        import time as _time
        if abs(_time.time() - auth_date) > 86400:
            return None

        user_str = parsed.get("user")
        if user_str:
            parsed["user"] = json.loads(user_str)
        return parsed
    except Exception:
        return None


def get_or_create_user(session: Session, telegram_id: int, username: str | None, first_name: str | None) -> User:
    """Получает или создаёт пользователя."""
    user = session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user:
        if username is not None or first_name is not None:
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
            session.commit()
        return user

    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
