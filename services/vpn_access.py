"""Общая проверка доступа к VPN (триал по users.created_at или оплата)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.subscription import Subscription
from db.models.user import User

TRIAL_DAYS = 3


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
