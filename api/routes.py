"""API маршруты для Mini App (Итерация 6.2: VLESS-ключ, GET /api/key)."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlalchemy.orm import joinedload

from api.auth import get_or_create_user, verify_init_data
from bot.config import VLESS_URL_TEMPLATE
from db.models import Payment, Server, Subscription, User
from db.session import get_session


def build_vless_url(uuid: str | None, server: Server | None = None) -> str | None:
    """
    Собирает VLESS-ссылку: подставляет UUID в шаблон.
    Если у сервера задан vless_url_template — используется он; иначе глобальный VLESS_URL_TEMPLATE.
    """
    if not uuid:
        return None
    template = None
    if server and getattr(server, "vless_url_template", None) and (server.vless_url_template or "").strip():
        template = (server.vless_url_template or "").strip()
    if not template and VLESS_URL_TEMPLATE:
        template = VLESS_URL_TEMPLATE
    if not template:
        return None
    return template.replace("{uuid}", uuid)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["mini-app"])


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    x_telegram_init_data: str | None = Header(None, alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
) -> User:
    """Извлекает пользователя по initData."""
    if not x_telegram_init_data:
        logger.warning("/api/me: 401 initData отсутствует (заголовок не передан)")
        raise HTTPException(status_code=401, detail="initData отсутствует")
    data = verify_init_data(x_telegram_init_data)
    if not data:
        logger.warning("/api/me: 401 Неверный initData (подпись или auth_date)")
        raise HTTPException(status_code=401, detail="Неверный initData")
    user_data = data.get("user")
    if not user_data:
        logger.warning("/api/me: 401 Нет данных пользователя в initData")
        raise HTTPException(status_code=401, detail="Нет данных пользователя")
    telegram_id = user_data.get("id")
    if not telegram_id:
        logger.warning("/api/me: 401 Нет telegram_id в user")
        raise HTTPException(status_code=401, detail="Нет telegram_id")
    user = get_or_create_user(
        db,
        telegram_id=int(telegram_id),
        username=user_data.get("username"),
        first_name=user_data.get("first_name"),
    )
    logger.info("/api/me: user id=%s telegram_id=%s", user.id, user.telegram_id)
    return user


def get_active_subscription(db: Session, user_id: int) -> Subscription | None:
    """Возвращает последнюю активную подписку пользователя (с загрузкой server для VLESS-ссылки)."""
    sub = db.scalars(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .where(Subscription.status.in_(["active", "expired"]))
        .order_by(Subscription.created_at.desc())
        .limit(1)
        .options(joinedload(Subscription.server))
    ).first()
    return sub


def get_pending_payment(db: Session, user_id: int) -> Payment | None:
    """Возвращает ожидающий платёж, если есть."""
    return db.scalars(
        select(Payment)
        .where(Payment.user_id == user_id)
        .where(Payment.status == "pending")
        .order_by(Payment.created_at.desc())
        .limit(1)
    ).first()


@router.get("/me")
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Профиль и статус подписки. Активная подписка имеет приоритет над pending-платежом."""
    sub = get_active_subscription(db, user.id)
    pending = get_pending_payment(db, user.id)
    if sub:
        logger.info("/api/me: user_id=%s sub_id=%s expires_at=%s -> state=active/expired", user.id, sub.id, sub.expires_at)
    elif pending:
        logger.info("/api/me: user_id=%s no sub, pending payment_id=%s -> state=payment_pending", user.id, pending.id)

    response = {
        "user": {
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
        },
    }

    if sub:
        expires_at = sub.expires_at
        if isinstance(expires_at, datetime) and expires_at.tzinfo:
            expires_str = expires_at.isoformat()
        else:
            expires_str = expires_at.strftime("%Y-%m-%dT%H:%M:%S") if expires_at else None

        now = datetime.now(timezone.utc)
        sub_expires = expires_at if (expires_at and expires_at.tzinfo) else (expires_at.replace(tzinfo=timezone.utc) if expires_at else now)
        is_expired = sub_expires < now

        sub_payload = {
            "status": "expired" if is_expired else sub.status,
            "expires_at": expires_str,
            "tariff_months": sub.tariff_months,
            "key": sub.uuid,
        }
        if sub.uuid and not is_expired:
            sub_payload["vless_url"] = build_vless_url(sub.uuid, sub.server)
        else:
            sub_payload["vless_url"] = None
        response["subscription"] = sub_payload
        response["state"] = "expired" if is_expired else "active"
    elif pending:
        response["subscription"] = None
        response["state"] = "payment_pending"
    else:
        response["subscription"] = None
        response["state"] = "no_subscription"

    return response


@router.get("/key")
def get_key(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Возвращает VLESS-ключ для активной подписки: vless_url, expires_at, days_left.
    Если активной подписки с ключом нет — vless_url null, days_left 0.
    """
    sub = get_active_subscription(db, user.id)
    now = datetime.now(timezone.utc)
    if not sub or not sub.uuid:
        return {"vless_url": None, "expires_at": None, "days_left": 0}
    expires_at = sub.expires_at
    if isinstance(expires_at, datetime) and expires_at.tzinfo:
        expires_str = expires_at.isoformat()
    else:
        expires_str = expires_at.strftime("%Y-%m-%dT%H:%M:%S") if expires_at else None
    sub_expires = expires_at if (expires_at and expires_at.tzinfo) else (expires_at.replace(tzinfo=timezone.utc) if expires_at else now)
    is_expired = sub_expires < now
    if is_expired:
        return {"vless_url": None, "expires_at": expires_str, "days_left": 0}
    delta = sub_expires - now
    days_left = max(0, delta.days)
    vless_url = build_vless_url(sub.uuid, sub.server)
    return {"vless_url": vless_url, "expires_at": expires_str, "days_left": days_left}
