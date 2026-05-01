"""Выдача и проверка access key для GET /servers?key=..."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models.access_key import AccessKey, AccessKeyDevice
from db.models.user import User
from services.vpn_access import user_has_vpn_access

logger = logging.getLogger(__name__)

_MAX_DEVICES = max(1, min(10, int(os.getenv("ACCESS_KEY_MAX_DEVICES", "3"))))


def access_key_max_devices() -> int:
    return _MAX_DEVICES


def generate_access_token() -> str:
    return secrets.token_urlsafe(24)


def ensure_access_key_after_payment(db: Session, user_id: int) -> None:
    """После успешной оплаты: один активный ключ на user, продление expires_at."""
    user = db.get(User, user_id)
    if user is None:
        return
    now = datetime.now(timezone.utc)
    if not user_has_vpn_access(user, now, db):
        logger.info("access_key: skip ensure user_id=%s (no paid access yet)", user_id)
        return

    row = db.scalar(select(AccessKey).where(AccessKey.user_id == user_id, AccessKey.status == "active"))
    exp = user.subscription_expires_at
    if row is None:
        token = generate_access_token()
        row = AccessKey(
            token=token,
            user_id=user_id,
            expires_at=exp,
            status="active",
        )
        db.add(row)
        logger.info("access_key: created user_id=%s", user_id)
    else:
        row.expires_at = exp
        row.status = "active"
        logger.info("access_key: updated user_id=%s", user_id)
    db.add(row)


def get_or_create_access_key_token(db: Session, user_id: int) -> str | None:
    """Токен для отображения в Mini App, если есть оплаченный доступ."""
    user = db.get(User, user_id)
    if user is None:
        return None
    now = datetime.now(timezone.utc)
    if not user_has_vpn_access(user, now, db):
        return None
    row = db.scalar(select(AccessKey).where(AccessKey.user_id == user_id, AccessKey.status == "active"))
    if row:
        row.expires_at = user.subscription_expires_at
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.token
    ensure_access_key_after_payment(db, user_id)
    db.commit()
    row = db.scalar(select(AccessKey).where(AccessKey.user_id == user_id, AccessKey.status == "active"))
    return row.token if row else None


def resolve_user_for_access_key_request(
    db: Session,
    *,
    token: str,
    platform: str,
    device_stable_id: str,
) -> tuple[User | None, str | None]:
    """
    Возвращает (user, None) при успехе.
    Иначе (user или None, error): invalid_key | subscription_required | device_limit
    """
    plat = platform.strip().lower()
    if plat not in ("android", "ios"):
        return None, "invalid_key"
    did = device_stable_id.strip()
    if len(did) < 4 or len(did) > 128:
        return None, "invalid_key"

    ak = db.scalar(select(AccessKey).where(AccessKey.token == token.strip(), AccessKey.status == "active"))
    if ak is None:
        return None, "invalid_key"

    user = db.get(User, ak.user_id)
    if user is None:
        return None, "invalid_key"

    now = datetime.now(timezone.utc)
    ak.expires_at = user.subscription_expires_at
    db.add(ak)

    if not user_has_vpn_access(user, now, db):
        db.commit()
        return user, "subscription_required"

    existing = db.scalar(
        select(AccessKeyDevice).where(
            AccessKeyDevice.access_key_id == ak.id,
            AccessKeyDevice.platform == plat,
            AccessKeyDevice.device_stable_id == did,
        )
    )
    if existing is not None:
        db.commit()
        return user, None

    n = db.scalar(select(func.count()).select_from(AccessKeyDevice).where(AccessKeyDevice.access_key_id == ak.id))
    if int(n or 0) >= access_key_max_devices():
        db.commit()
        return user, "device_limit"

    db.add(AccessKeyDevice(access_key_id=ak.id, platform=plat, device_stable_id=did))
    db.commit()
    return user, None
