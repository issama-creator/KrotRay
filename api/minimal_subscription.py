"""Продление users.subscription_expires_at для key-factory (без привязки к Subscription/Xray)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from db.models.user import User


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def bump_subscription_expires_at(db: Session, *, user_id: int, tariff_months: int, days_per_month: int = 30) -> None:
    """Стек продления: новый срок = max(now, текущий expires) + tariff_months * days."""
    now = datetime.now(timezone.utc)
    delta = timedelta(days=int(tariff_months) * int(days_per_month))
    user = db.get(User, user_id)
    if user is None:
        return
    cur = user.subscription_expires_at
    if cur is not None:
        cur_u = _as_utc(cur)
        base = max(now, cur_u)
    else:
        base = now
    user.subscription_expires_at = base + delta
    db.add(user)
