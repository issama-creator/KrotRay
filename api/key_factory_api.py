"""
Key factory: выдача 4 серверов (2 wifi + 2 bypass) из Redis, доступ по users + оплата.

Внешний идентификатор клиента — **telegram_id** (тот же пользователь, что в Mini App / платежах).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from redis import Redis
from redis.exceptions import LockError
from sqlalchemy.orm import Session

from api.auth import get_or_create_user
from db.models.user import User
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
    return {
        "Retry-After": "1",
        "X-Retry-Jitter-Ms-Min": "100",
        "X-Retry-Jitter-Ms-Max": "300",
    }


def _assignment_lock(redis_client: Redis, telegram_id: int):
    return redis_client.lock(
        f"lock:kf:tg:{telegram_id}",
        timeout=30,
        blocking_timeout=25,
    )


class RefreshBody(BaseModel):
    telegram_id: int = Field(..., ge=1, description="Telegram user id (тот же, что в initData)")


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ensure_user(db: Session, telegram_id: int) -> User:
    return get_or_create_user(db, telegram_id=telegram_id, username=None, first_name=None)


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


@router.get(
    "/servers",
    summary="Получить закреплённую четвёрку серверов",
    response_description="Список серверов или subscription_required",
)
def get_servers(
    telegram_id: int = Query(..., ge=1, description="Telegram user id"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    now_dt = datetime.now(timezone.utc)
    user = _ensure_user(db, telegram_id)
    if not _has_access(user, now_dt):
        return {"error": "subscription_required"}

    redis_client = get_redis()
    cached = get_cached_user(redis_client, telegram_id)
    if cached:
        return {"servers": _normalize_servers(list(cached.get("servers") or []))}

    lock = _assignment_lock(redis_client, telegram_id)
    try:
        with lock:
            cached = get_cached_user(redis_client, telegram_id)
            if cached:
                return {"servers": _normalize_servers(list(cached.get("servers") or []))}

            all_servers = load_all_servers(redis_client)
            try:
                assigned = pick_servers_dual(all_servers)
            except ValueError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            apply_assign(redis_client, assigned, amount=0.25)
            next_update = time.time() + REFRESH_COOLDOWN_SEC
            save_cached_user(redis_client, telegram_id, assigned, next_update)
            logger.info(
                "assign telegram_id=%s internal_user_id=%s servers=%s",
                telegram_id,
                user.id,
                [s["id"] for s in assigned],
            )
            return {"servers": _normalize_servers(assigned)}
    except LockError:
        cached = get_cached_user(redis_client, telegram_id)
        if cached:
            return {"servers": _normalize_servers(list(cached.get("servers") or []))}
        logger.warning("assign lock wait exceeded telegram_id=%s", telegram_id)
        raise HTTPException(
            status_code=503,
            detail="assignment_busy_retry",
            headers=_busy_assignment_headers(),
        ) from None


@router.post("/refresh", summary="Перевыбрать серверы (не чаще чем раз в cooldown)")
def refresh_servers(body: RefreshBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    now_dt = datetime.now(timezone.utc)
    user = _ensure_user(db, body.telegram_id)
    if not _has_access(user, now_dt):
        return {"error": "subscription_required"}

    redis_client = get_redis()
    tid = body.telegram_id

    lock = _assignment_lock(redis_client, tid)
    try:
        with lock:
            cached = get_cached_user(redis_client, tid)
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
            save_cached_user(redis_client, tid, new_servers, now_ts + REFRESH_COOLDOWN_SEC)
            logger.info(
                "refresh telegram_id=%s internal_user_id=%s old_servers=%s new_servers=%s",
                tid,
                user.id,
                [s["id"] for s in old_servers],
                [s["id"] for s in new_servers],
            )
            return {"servers": _normalize_servers(new_servers)}
    except LockError:
        logger.warning("refresh lock wait exceeded telegram_id=%s", tid)
        raise HTTPException(
            status_code=503,
            detail="assignment_busy_retry",
            headers=_busy_assignment_headers(),
        ) from None


@router.get("/contract", summary="Контракт API для клиента (JSON)")
def api_contract() -> dict[str, Any]:
    return {
        "identifier": "Клиент передаёт telegram_id (число из Telegram WebApp / Login). Совпадает с пользователем оплаты в Mini App.",
        "endpoints": [
            {
                "method": "GET",
                "path": "/servers",
                "query": {"telegram_id": "integer, required"},
                "responses": {
                    "200": {
                        "servers": "[{id, type: wifi|bypass, priority: 1..2}] — всегда 4 записи при успехе",
                        "error": "subscription_required — нет триала и нет subscription_expires_at",
                    },
                    "503": {
                        "detail": "assignment_busy_retry — не взяли лок вовремя; заголовки Retry-After / X-Retry-Jitter-*",
                        "detail_alt": "текст ошибки выбора серверов (мало alive wifi/bypass)",
                    },
                },
            },
            {
                "method": "POST",
                "path": "/refresh",
                "body": {"telegram_id": "integer"},
                "responses": {
                    "200": {"servers": "как в GET"},
                    "400": "validation",
                    "200_alt": "{ \"error\": \"subscription_required\" } при истечении триала и подписки",
                    "409": "assignment_not_found — нет кэша user:kf:*, сначала GET /servers",
                    "429": "rate_limited — раньше next_update",
                    "503": "assignment_busy_retry или ошибка пула серверов",
                },
            },
            {
                "method": "POST",
                "path": "/api/payments/create",
                "headers": {"X-Telegram-Init-Data": "обязательно для Mini App"},
                "note": "После оплаты ЮKassa шлёт webhook на /api/payments/webhook — продлевается users.subscription_expires_at",
            },
        ],
        "payments_webhook_url_hint": "Настроить в ЮKassa: POST https://<host>/api/payments/webhook",
        "env": {
            "MINIMAL_PAYMENT_WEBHOOK": "1 — только продление users.subscription_expires_at и статус payment (без Xray/Subscription/cp)",
            "REDIS_URL или EDGE_REDIS_URL": "Redis для балансировки",
            "DATABASE_URL": "PostgreSQL",
            "YOOKASSA_*": "магазин ЮKassa",
        },
        "redis_catalog": "servers:list JSON массив id; server:{id} hash: type, count, max, status, last_assigned, host — см. scripts/seed_redis_key_factory.py",
    }
