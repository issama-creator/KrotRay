"""
Key factory: 4 сервера из Redis.

Идентификация (ровно один вариант):
- Нативное приложение: platform + device_stable_id (ANDROID_ID / аналог + триал на устройство).
- Mini App / уже только Telegram: telegram_id.

Redis-кэш назначения: user:kf:{users.id} (внутренний account_id).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from redis import Redis
from redis.exceptions import LockError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.auth import get_or_create_user
from db.models.payment import Payment
from db.models.subscription import Subscription
from db.models.user import User
from db.session import get_session
from services.minimal_lb import (
    apply_assign,
    apply_deassign,
    get_cached_user,
    get_redis,
    invalidate_user_assignment,
    load_all_servers,
    pick_servers_dual,
    save_cached_user,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["key-factory"])

TRIAL_DAYS = 3
REFRESH_COOLDOWN_SEC = 5 * 60

_ALLOWED_PLATFORMS = frozenset({"android", "ios"})


def _busy_assignment_headers() -> dict[str, str]:
    return {
        "Retry-After": "1",
        "X-Retry-Jitter-Ms-Min": "100",
        "X-Retry-Jitter-Ms-Max": "300",
    }


def _assignment_lock(redis_client: Redis, account_id: int):
    return redis_client.lock(
        f"lock:kf:acct:{account_id}",
        timeout=30,
        blocking_timeout=25,
    )


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_device_stable_id(raw: str) -> str:
    s = raw.strip()
    if len(s) < 4 or len(s) > 128:
        raise HTTPException(status_code=400, detail="invalid device_stable_id")
    return s


def _ensure_user_device(db: Session, *, platform: str, device_stable_id: str) -> User:
    did = _normalize_device_stable_id(device_stable_id)
    if platform not in _ALLOWED_PLATFORMS:
        raise HTTPException(status_code=400, detail="platform must be android or ios")
    user = db.scalar(
        select(User).where(User.platform == platform, User.device_stable_id == did),
    )
    if user:
        return user
    user = User(
        telegram_id=None,
        platform=platform,
        device_stable_id=did,
        username=None,
        first_name=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("key_factory: new device user id=%s platform=%s", user.id, platform)
    return user


def _resolve_user_for_servers(
    db: Session,
    *,
    telegram_id: int | None,
    platform: str | None,
    device_stable_id: str | None,
) -> User:
    if telegram_id is not None:
        if platform is not None or device_stable_id is not None:
            raise HTTPException(
                status_code=400,
                detail="use either telegram_id or (platform + device_stable_id), not both",
            )
        return get_or_create_user(db, telegram_id=telegram_id, username=None, first_name=None)

    if platform is None or device_stable_id is None:
        raise HTTPException(
            status_code=400,
            detail="provide telegram_id OR platform and device_stable_id",
        )
    plat = platform.strip().lower()
    return _ensure_user_device(db, platform=plat, device_stable_id=device_stable_id)


def _has_access(user: User, now_dt: datetime) -> bool:
    created_at = _to_utc(user.created_at) or now_dt
    trial_until = created_at + timedelta(days=TRIAL_DAYS)
    if now_dt < trial_until:
        return True
    sub_expires_at = _to_utc(user.subscription_expires_at)
    return bool(sub_expires_at and sub_expires_at > now_dt)


def _normalize_servers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        out.append(
            {
                "id": str(item.get("id")),
                "type": str(item.get("type")),
                "priority": int(item.get("priority", 0)),
            }
        )
    return out


class RefreshBody(BaseModel):
    telegram_id: int | None = Field(default=None, ge=1)
    platform: Literal["android", "ios"] | None = None
    device_stable_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _one_identity(self) -> RefreshBody:
        has_tg = self.telegram_id is not None
        has_dev = bool(self.platform and self.device_stable_id)
        if has_tg == has_dev:
            raise ValueError("provide either telegram_id or (platform + device_stable_id)")
        return self


class AttachBody(BaseModel):
    platform: Literal["android", "ios"]
    device_stable_id: str = Field(..., min_length=4, max_length=128)
    telegram_id: int = Field(..., ge=1)


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def _payload_servers_ok(user: User, servers_norm: list[dict[str, Any]]) -> dict[str, Any]:
    return {"account_id": user.id, "servers": servers_norm}


@router.get("/servers", summary="Четвёрка серверов (trial / подписка)")
def get_servers(
    telegram_id: int | None = Query(None, ge=1),
    platform: str | None = Query(None, description="android | ios"),
    device_stable_id: str | None = Query(None, max_length=128),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    now_dt = datetime.now(timezone.utc)
    user = _resolve_user_for_servers(db, telegram_id=telegram_id, platform=platform, device_stable_id=device_stable_id)
    if not _has_access(user, now_dt):
        return {"account_id": user.id, "error": "subscription_required"}

    redis_client = get_redis()
    aid = user.id
    cached = get_cached_user(redis_client, aid)
    if cached:
        return _payload_servers_ok(user, _normalize_servers(list(cached.get("servers") or [])))

    lock = _assignment_lock(redis_client, aid)
    try:
        with lock:
            cached = get_cached_user(redis_client, aid)
            if cached:
                return _payload_servers_ok(user, _normalize_servers(list(cached.get("servers") or [])))

            all_servers = load_all_servers(redis_client)
            try:
                assigned = pick_servers_dual(all_servers)
            except ValueError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            apply_assign(redis_client, assigned, amount=0.25)
            next_update = time.time() + REFRESH_COOLDOWN_SEC
            save_cached_user(redis_client, aid, assigned, next_update)
            logger.info("assign account_id=%s servers=%s", aid, [s["id"] for s in assigned])
            return _payload_servers_ok(user, _normalize_servers(assigned))
    except LockError:
        cached = get_cached_user(redis_client, aid)
        if cached:
            return _payload_servers_ok(user, _normalize_servers(list(cached.get("servers") or [])))
        logger.warning("assign lock wait exceeded account_id=%s", aid)
        raise HTTPException(
            status_code=503,
            detail="assignment_busy_retry",
            headers=_busy_assignment_headers(),
        ) from None


@router.post("/refresh", summary="Перевыбор серверов (cooldown)")
def refresh_servers(body: RefreshBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    now_dt = datetime.now(timezone.utc)
    user = _resolve_user_for_servers(
        db,
        telegram_id=body.telegram_id,
        platform=body.platform,
        device_stable_id=body.device_stable_id,
    )
    if not _has_access(user, now_dt):
        return {"account_id": user.id, "error": "subscription_required"}

    redis_client = get_redis()
    aid = user.id

    lock = _assignment_lock(redis_client, aid)
    try:
        with lock:
            cached = get_cached_user(redis_client, aid)
            if not cached:
                raise HTTPException(status_code=409, detail="assignment_not_found")

            now_ts = time.time()
            next_update = float(cached.get("next_update") or 0.0)
            if now_ts < next_update:
                raise HTTPException(status_code=429, detail="rate_limited")

            old_servers = _normalize_servers(list(cached.get("servers") or []))
            apply_deassign(redis_client, old_servers, amount=0.25)

            all_servers = load_all_servers(redis_client)
            try:
                new_servers = pick_servers_dual(all_servers)
            except ValueError as exc:
                apply_assign(redis_client, old_servers, amount=0.25)
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            apply_assign(redis_client, new_servers, amount=0.25)
            save_cached_user(redis_client, aid, new_servers, now_ts + REFRESH_COOLDOWN_SEC)
            logger.info(
                "refresh account_id=%s old=%s new=%s",
                aid,
                [s["id"] for s in old_servers],
                [s["id"] for s in new_servers],
            )
            return _payload_servers_ok(user, _normalize_servers(new_servers))
    except LockError:
        logger.warning("refresh lock wait exceeded account_id=%s", aid)
        raise HTTPException(
            status_code=503,
            detail="assignment_busy_retry",
            headers=_busy_assignment_headers(),
        ) from None


@router.post("/attach", summary="Привязать устройство к Telegram (после бота)")
def attach_telegram(body: AttachBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Сливает строку «только устройство» с аккаунтом Mini App (telegram_id), инвалидирует кэш назначения."""
    did = _normalize_device_stable_id(body.device_stable_id)
    dev_user = db.scalar(select(User).where(User.platform == body.platform, User.device_stable_id == did))
    if dev_user is None:
        raise HTTPException(status_code=404, detail="device_user_not_found")

    if dev_user.telegram_id is not None and dev_user.telegram_id != body.telegram_id:
        raise HTTPException(status_code=409, detail="device_already_linked_other_telegram")

    tg_user = db.scalar(select(User).where(User.telegram_id == body.telegram_id))
    redis_client = get_redis()

    if tg_user is None:
        invalidate_user_assignment(redis_client, dev_user.id)
        link_now = datetime.now(timezone.utc)
        dev_user.telegram_id = body.telegram_id
        dev_user.telegram_linked_at = link_now
        db.commit()
        db.refresh(dev_user)
        return {"ok": True, "account_id": dev_user.id, "merged": False}

    if tg_user.id == dev_user.id:
        return {"ok": True, "account_id": tg_user.id, "merged": False}

    if tg_user.device_stable_id and (
        tg_user.device_stable_id != did or tg_user.platform != body.platform
    ):
        raise HTTPException(status_code=409, detail="telegram_already_linked_other_device")

    invalidate_user_assignment(redis_client, dev_user.id)
    invalidate_user_assignment(redis_client, tg_user.id)

    ca_dev = _to_utc(dev_user.created_at) or datetime.now(timezone.utc)
    ca_tg = _to_utc(tg_user.created_at) or datetime.now(timezone.utc)
    tg_user.created_at = min(ca_dev, ca_tg)

    sub_d = _to_utc(dev_user.subscription_expires_at)
    sub_t = _to_utc(tg_user.subscription_expires_at)
    if sub_d and sub_t:
        tg_user.subscription_expires_at = max(sub_d, sub_t)
    elif sub_d:
        tg_user.subscription_expires_at = dev_user.subscription_expires_at
    # else keep tg subscription

    tg_user.platform = body.platform
    tg_user.device_stable_id = did
    if tg_user.telegram_linked_at is None:
        tg_user.telegram_linked_at = datetime.now(timezone.utc)

    dev_pk = dev_user.id
    db.execute(update(Payment).where(Payment.user_id == dev_pk).values(user_id=tg_user.id))
    db.execute(update(Subscription).where(Subscription.user_id == dev_pk).values(user_id=tg_user.id))

    db.delete(dev_user)
    db.commit()
    db.refresh(tg_user)
    logger.info(
        "attach merge dev_id=%s -> tg_account_id=%s telegram_id=%s",
        dev_pk,
        tg_user.id,
        body.telegram_id,
    )
    return {"ok": True, "account_id": tg_user.id, "merged": True}


@router.get("/contract", summary="Контракт API (JSON)")
def api_contract() -> dict[str, Any]:
    return {
        "identity_modes": [
            "Нативное приложение: GET /servers?platform=android|ios&device_stable_id=... (триал на пару platform+device)",
            "Mini App / только Telegram: GET /servers?telegram_id=...",
            "Не смешивать параметры в одном запросе.",
        ],
        "responses": {
            "success_includes": {"account_id": "внутренний users.id (поддержка, логи)", "servers": "4 объекта"},
            "subscription_required": '{"account_id", "error":"subscription_required"}',
        },
        "attach": {
            "method": "POST",
            "path": "/attach",
            "body": {"platform": "android|ios", "device_stable_id": "str", "telegram_id": "int"},
            "note": "Вызывать после того как пользователь открыл бота / выдал telegram_id. merge=True если сливали с аккаунтом Mini App.",
        },
        "redis_user_key": "user:kf:{account_id}",
        "payments": "POST /api/payments/create + webhook — продлевает subscription_expires_at по users.id",
        "redis_catalog": "scripts/seed_redis_key_factory.py",
    }
