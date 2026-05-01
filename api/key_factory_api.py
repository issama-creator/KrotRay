from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from redis import Redis
from redis.exceptions import LockError
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.session import get_session
from services.minimal_lb import (
    apply_assign,
    apply_deassign,
    get_cached_user,
    get_redis,
    load_all_servers,
    pick_servers_dual,
    save_cached_user,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["key-factory"])


TRIAL_DAYS = 3
REFRESH_COOLDOWN_SEC = 5 * 60


def _busy_assignment_headers() -> dict[str, str]:
    """
    Подсказка клиенту при contention по локу.
    Retry-After по RFC — целые секунды; точный backoff с jitter (100–300 ms) — в кастомных заголовках.
    """
    return {
        "Retry-After": "1",
        "X-Retry-Jitter-Ms-Min": "100",
        "X-Retry-Jitter-Ms-Max": "300",
    }


def _user_assignment_lock(redis_client: Redis, user_id: int):
    """Сериализует первое назначение и refresh для одного user_id (защита от двойного +0.25)."""
    # timeout — TTL лока в Redis (если процесс умрёт до release). Внутри лока только Redis + CPU (без внешней сети).
    # blocking_timeout — сколько ждать захват; при истечении — LockError → см. обработчики ниже.
    return redis_client.lock(
        f"lock:kf:user:{user_id}",
        timeout=30,
        blocking_timeout=25,
    )


class RefreshBody(BaseModel):
    user_id: int = Field(..., ge=1)


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def _to_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None


def _ensure_user(db: Session, user_id: int) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT id, created_at, subscription_expires_at
            FROM users
            WHERE id = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    if row:
        return dict(row)

    created = db.execute(
        text(
            """
            INSERT INTO users (id, telegram_id, username, first_name, created_at, subscription_expires_at)
            VALUES (:user_id, :telegram_id, NULL, NULL, NOW(), NULL)
            ON CONFLICT (id) DO UPDATE SET id = EXCLUDED.id
            RETURNING id, created_at, subscription_expires_at
            """
        ),
        {"user_id": user_id, "telegram_id": user_id},
    ).mappings().first()
    db.commit()
    if created is None:
        raise HTTPException(status_code=500, detail="user_create_failed")
    return dict(created)


def _has_access(user_row: dict[str, Any], now_dt: datetime) -> bool:
    created_at = _to_utc(user_row.get("created_at")) or now_dt
    trial_until = created_at + timedelta(days=TRIAL_DAYS)
    if now_dt < trial_until:
        return True
    sub_expires_at = _to_utc(user_row.get("subscription_expires_at"))
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


@router.get("/servers")
def get_servers(user_id: int = Query(..., ge=1), db: Session = Depends(get_db)) -> dict[str, Any]:
    now_dt = datetime.now(timezone.utc)
    user = _ensure_user(db, user_id=user_id)
    if not _has_access(user, now_dt):
        return {"error": "subscription_required"}

    redis_client = get_redis()
    cached = get_cached_user(redis_client, user_id)
    if cached:
        return {"servers": _normalize_servers(list(cached.get("servers") or []))}

    lock = _user_assignment_lock(redis_client, user_id)
    try:
        with lock:
            cached = get_cached_user(redis_client, user_id)
            if cached:
                return {"servers": _normalize_servers(list(cached.get("servers") or []))}

            all_servers = load_all_servers(redis_client)
            try:
                assigned = pick_servers_dual(all_servers)
            except ValueError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            apply_assign(redis_client, assigned, amount=0.25)
            next_update = time.time() + REFRESH_COOLDOWN_SEC
            save_cached_user(redis_client, user_id, assigned, next_update)
            logger.info("assign user_id=%s servers=%s", user_id, [s["id"] for s in assigned])
            return {"servers": _normalize_servers(assigned)}
    except LockError:
        cached = get_cached_user(redis_client, user_id)
        if cached:
            return {"servers": _normalize_servers(list(cached.get("servers") or []))}
        logger.warning("assign lock wait exceeded user_id=%s", user_id)
        raise HTTPException(
            status_code=503,
            detail="assignment_busy_retry",
            headers=_busy_assignment_headers(),
        ) from None


@router.post("/refresh")
def refresh_servers(body: RefreshBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    now_dt = datetime.now(timezone.utc)
    user = _ensure_user(db, user_id=body.user_id)
    if not _has_access(user, now_dt):
        return {"error": "subscription_required"}

    redis_client = get_redis()

    lock = _user_assignment_lock(redis_client, body.user_id)
    try:
        with lock:
            cached = get_cached_user(redis_client, body.user_id)
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
            save_cached_user(redis_client, body.user_id, new_servers, now_ts + REFRESH_COOLDOWN_SEC)
            logger.info(
                "refresh user_id=%s old_servers=%s new_servers=%s",
                body.user_id,
                [s["id"] for s in old_servers],
                [s["id"] for s in new_servers],
            )
            return {"servers": _normalize_servers(new_servers)}
    except LockError:
        logger.warning("refresh lock wait exceeded user_id=%s", body.user_id)
        raise HTTPException(
            status_code=503,
            detail="assignment_busy_retry",
            headers=_busy_assignment_headers(),
        ) from None
