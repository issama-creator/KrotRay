"""Общая проверка доступа к VPN (триал по users.created_at или оплата)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.subscription import Subscription
from db.models.user import User

TRIAL_DAYS = 3

_ALLOWED_NATIVE_PLATFORMS = frozenset({"android", "ios"})


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def resolve_user_device_then_telegram(
    db: Session,
    *,
    platform: str,
    device_stable_id: str,
    telegram_id: int | None,
) -> tuple[User | None, Literal["device", "telegram"] | None]:
    """
    Кто владелец триала/подписки в UI: сначала строка users по устройству (как GET /servers без ключа),
    иначе — по telegram_id (если передан и пользователь уже есть в БД).
    Не создаёт строк — только поиск (на GET /api/config без побочных INSERT).
    """
    plat = platform.strip().lower()
    if plat not in _ALLOWED_NATIVE_PLATFORMS:
        plat = "android"
    did = device_stable_id.strip()
    if 4 <= len(did) <= 128:
        row = db.scalar(
            select(User).where(User.platform == plat, User.device_stable_id == did),
        )
        if row is not None:
            return row, "device"
    if telegram_id is not None and telegram_id >= 1:
        row = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if row is not None:
            return row, "telegram"
    return None, None


def access_subscription_snapshot(user: User | None, now: datetime, db: Session) -> dict[str, Any]:
    """
    Один снимок для UI: триал и оплата по строке User — те же правила, что user_has_vpn_access.
    Используется /api/config; доступ к туннелю на GET /servers по-прежнему через user_has_vpn_access.
    """
    if user is None:
        return {
            "user_id": None,
            "account_registered": False,
            "has_access": False,
            "trial_active": False,
            "subscription_active": False,
            "trial_until_ts": 0,
            "subscription_until_ts": 0,
        }

    created_at = _to_utc(user.created_at) or now
    trial_end = created_at + timedelta(days=TRIAL_DAYS)
    trial_until_ts = int(trial_end.timestamp())

    sub_col = _to_utc(user.subscription_expires_at)
    paid_from_user = bool(sub_col and sub_col > now)
    sub_ts = int(sub_col.timestamp()) if paid_from_user and sub_col else 0

    row = db.scalars(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .where(Subscription.status == "active")
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    ).first()
    paid_from_sub = False
    if row and row.expires_at:
        exp = _to_utc(row.expires_at)
        if exp and exp > now:
            paid_from_sub = True
            sub_ts = max(sub_ts, int(exp.timestamp()))

    has_paid = paid_from_user or paid_from_sub
    in_trial_calendar = now < trial_end
    trial_active = bool(in_trial_calendar and not has_paid)
    subscription_active = bool(has_paid)

    return {
        "user_id": user.id,
        "account_registered": True,
        "has_access": user_has_vpn_access(user, now, db),
        "trial_active": trial_active,
        "subscription_active": subscription_active,
        "trial_until_ts": trial_until_ts,
        "subscription_until_ts": sub_ts,
    }


def user_has_vpn_access(user: User, now: datetime, db: Session | None = None) -> bool:
    """
    Триал: created_at + TRIAL_DAYS.
    Оплата: users.subscription_expires_at или активная строка subscriptions (если передан db).
    """
    created_at = _to_utc(user.created_at) or now
    trial_until = created_at + timedelta(days=TRIAL_DAYS)
    if now < trial_until:
        return True
    sub_exp = _to_utc(user.subscription_expires_at)
    if sub_exp and sub_exp > now:
        return True
    if db is not None:
        row = db.scalars(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .where(Subscription.status == "active")
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        ).first()
        if row and row.expires_at:
            exp = _to_utc(row.expires_at)
            if exp and exp > now:
                return True
    return False
