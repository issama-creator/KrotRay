"""
Edge LB: выдача 4 менее нагруженных exit + heartbeat по device_id.

Таблицы: edge_users, edge_servers, edge_devices.
Эндпоинты: POST /config, POST /ping.
"""
from __future__ import annotations

import logging
import os
import random
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cp_api import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["edge-lb"])

# Временно расширили окно «онлайн» для тестов, чтобы нагрузка не обнулялась каждые 90 сек.
ONLINE_SEC = 86400
# Из топа наименее загруженных выбираем случайные.
TOP_LEAST_LOADED = 10
RETURN_PAIRS = 4
# Подготовка к split-пулам: 2 обычных + 2 обходных.
RETURN_DIRECT = 2
RETURN_BYPASS = 2
# Имена пулов можно переопределить через env для гибкой раскладки серверов.
EDGE_POOL_DIRECT = os.getenv("EDGE_POOL_DIRECT", "nl")
EDGE_POOL_BYPASS = os.getenv("EDGE_POOL_BYPASS", "bypass")
EDGE_POOL_SHARED = os.getenv("EDGE_POOL_SHARED", "shared")
TRIAL_DAYS = 3


class ConfigBody(BaseModel):
    device_id: str = Field(..., min_length=1)
    key: str | None = None


class PingBody(BaseModel):
    device_id: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)
    server_id: int = Field(..., description="id exit-сервера (type=exit)")


def _normalize_device_id(raw: str) -> str:
    did = raw.strip()
    if not did:
        raise HTTPException(status_code=400, detail="device_id is required")
    return did


def _fetch_valid_edge_user(db: Session, *, key: str, device_id: str) -> Any | None:
    return db.execute(
        text(
            """
            SELECT id, key, device_id, expires_at, is_active
            FROM edge_users
            WHERE key = :key
              AND device_id = :device_id
              AND is_active = true
              AND expires_at > NOW()
            """
        ),
        {"key": key, "device_id": device_id},
    ).mappings().first()


def _resolve_or_create_key(db: Session, body: ConfigBody) -> tuple[str, str | None]:
    did = _normalize_device_id(body.device_id)
    if body.key:
        row = _fetch_valid_edge_user(db, key=body.key.strip(), device_id=did)
        if not row:
            return "", "subscription_required"
        return str(row["key"]), None

    # Race-safe create: если два запроса прилетели одновременно на один device_id,
    # второй не падает на UNIQUE, а просто читает уже созданную строку.
    new_key = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO edge_users (key, device_id, expires_at, is_active, created_at)
            VALUES (:key, :device_id, NOW() + (:trial_days * INTERVAL '1 day'), true, NOW())
            ON CONFLICT (device_id) DO NOTHING
            """
        ),
        {"key": new_key, "device_id": did, "trial_days": TRIAL_DAYS},
    )
    db.commit()

    current = db.execute(
        text(
            """
            SELECT key, expires_at, is_active
            FROM edge_users
            WHERE device_id = :device_id
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"device_id": did},
    ).mappings().first()
    if not current:
        logger.error("edge_config: edge_users row missing after upsert for device_id=%s", did)
        return "", "internal_error"

    valid = _fetch_valid_edge_user(db, key=str(current["key"]), device_id=did)
    if not valid:
        return "", "subscription_required"
    return str(valid["key"]), None


@router.post("/ping")
def post_ping(body: PingBody, db: Session = Depends(get_db)) -> dict[str, bool]:
    did = _normalize_device_id(body.device_id)
    key = body.key.strip()
    user = _fetch_valid_edge_user(db, key=key, device_id=did)
    if not user:
        raise HTTPException(status_code=403, detail="subscription_required")

    row = db.execute(
        text(
            """
            SELECT id, type FROM edge_servers
            WHERE id = :sid AND is_active = true
            """
        ),
        {"sid": body.server_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=400, detail="unknown or inactive server_id")
    if row[1] != "exit":
        raise HTTPException(status_code=400, detail="server_id must be an exit server")

    ping_too_soon = db.execute(
        text(
            """
            SELECT (last_seen > NOW() - INTERVAL '30 seconds') AS too_soon
            FROM edge_devices
            WHERE device_id = :device_id
            """
        ),
        {"device_id": did},
    ).scalar_one_or_none()
    if bool(ping_too_soon):
        return {"ok": True}

    # PostgreSQL: ON CONFLICT по уникальному device_id
    db.execute(
        text(
            """
            INSERT INTO edge_devices (device_id, server_id, last_seen)
            VALUES (:device_id, :server_id, NOW())
            ON CONFLICT (device_id) DO UPDATE SET
                server_id = EXCLUDED.server_id,
                last_seen = NOW()
            """
        ),
        {"device_id": did, "server_id": body.server_id},
    )
    db.commit()
    return {"ok": True}


def _fetch_exits_least_loaded(db: Session, *, limit: int, pool: str | None = None) -> list[Any]:
    sql = """
            SELECT
                s.id,
                s.name,
                s.host,
                s.group_id,
                COALESCE(s.pool, :shared_pool) AS pool,
                COALESCE(cnt.c, 0)::int AS load
            FROM edge_servers s
            LEFT JOIN (
                SELECT d.server_id, COUNT(*)::int AS c
                FROM edge_devices d
                WHERE d.last_seen > NOW() - (:online_sec * INTERVAL '1 second')
                GROUP BY d.server_id
            ) cnt ON cnt.server_id = s.id
            WHERE s.type = 'exit' AND s.is_active = true
              AND (:pool IS NULL OR COALESCE(s.pool, :shared_pool) = :pool)
            ORDER BY load ASC, s.id ASC
            LIMIT :top_n
            """
    return list(
        db.execute(
            text(sql),
            {"online_sec": ONLINE_SEC, "top_n": limit, "pool": pool, "shared_pool": EDGE_POOL_SHARED},
        )
        .mappings()
        .all()
    )


def _fetch_bridges_by_group(db: Session, *, group_ids: list[str], pool: str | None = None) -> dict[str, Any]:
    if not group_ids:
        return {}
    sql = """
        SELECT
            b.id,
            b.group_id,
            b.host,
            COALESCE(b.pool, :shared_pool) AS pool
        FROM edge_servers b
        WHERE b.type = 'bridge'
          AND b.is_active = true
          AND b.group_id = ANY(:group_ids)
          AND (:pool IS NULL OR COALESCE(b.pool, :shared_pool) = :pool)
        ORDER BY b.id ASC
    """
    rows = list(
        db.execute(
            text(sql),
            {"group_ids": group_ids, "pool": pool, "shared_pool": EDGE_POOL_SHARED},
        )
        .mappings()
        .all()
    )
    by_group: dict[str, Any] = {}
    for row in rows:
        gid = str(row["group_id"] or "")
        if gid and gid not in by_group:
            by_group[gid] = row
    return by_group


def _pick_best_tier_random(rows: list[Any], *, k: int) -> list[Any]:
    """
    Из уже отсортированных по load ASC строк выбираем случайные k,
    но только из "лучшего" набора: включаем следующий tier нагрузки
    только если иначе не набирается k кандидатов.
    """
    if not rows or k <= 0:
        return []

    # rows уже ORDER BY load ASC, id ASC
    cutoff_load: int | None = None
    count = 0
    for r in rows:
        if cutoff_load is None:
            cutoff_load = int(r["load"])
        if int(r["load"]) != cutoff_load and count >= k:
            break
        cutoff_load = int(r["load"])
        count += 1

    if cutoff_load is None:
        return []

    candidates = [r for r in rows if int(r["load"]) <= cutoff_load]
    kk = min(k, len(candidates))
    return random.sample(candidates, k=kk)


def _append_direct_unique(out: list[dict[str, Any]], rows: list[Any], *, cap: int) -> None:
    used_ids = {int(item["id"]) for item in out if "id" in item}
    for ex in rows:
        sid = int(ex["id"])
        if sid in used_ids:
            continue
        out.append(
            {
                "id": sid,
                "host": ex["host"],
                "port": 443,
                "mode": "direct",
                "pool": ex["pool"],
            }
        )
        used_ids.add(sid)
        if len(out) >= cap:
            return


@router.post("/config")
def post_edge_config(body: ConfigBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Авторизация по key/device_id.
    Основной режим: 2 direct + 2 bypass (раздельные пулы exit, нагрузка только по exit).
    Для bypass по group_id добавляется связанный bridge.
    Fallback (на старых данных): 4 сервера из общего пула.
    """
    resolved_key, auth_error = _resolve_or_create_key(db, body)
    if auth_error == "subscription_required":
        raise HTTPException(status_code=403, detail="subscription_required")
    if auth_error == "internal_error":
        raise HTTPException(status_code=500, detail="internal_error")

    direct_rows = _fetch_exits_least_loaded(db, limit=TOP_LEAST_LOADED, pool=EDGE_POOL_DIRECT)
    bypass_rows = _fetch_exits_least_loaded(db, limit=TOP_LEAST_LOADED, pool=EDGE_POOL_BYPASS)

    chosen_direct = _pick_best_tier_random(direct_rows, k=RETURN_DIRECT)
    chosen_bypass_exits = _pick_best_tier_random(bypass_rows, k=RETURN_BYPASS)

    servers_out: list[dict[str, Any]] = []
    for ex in chosen_direct:
        servers_out.append(
            {
                "id": ex["id"],
                "host": ex["host"],
                "port": 443,
                "mode": "direct",
                "pool": ex["pool"],
            }
        )

    bypass_group_ids = [str(ex["group_id"]) for ex in chosen_bypass_exits if ex.get("group_id")]
    bridges_by_group = _fetch_bridges_by_group(db, group_ids=bypass_group_ids, pool=EDGE_POOL_BYPASS)
    for ex in chosen_bypass_exits:
        gid = str(ex.get("group_id") or "")
        bridge = bridges_by_group.get(gid)
        if not bridge:
            # Без bridge обходной маршрут неполный — пропускаем.
            continue
        servers_out.append(
            {
                "id": ex["id"],
                "host": ex["host"],
                "port": 443,
                "mode": "bypass",
                "pool": ex["pool"],
                "bridge": {
                    "id": bridge["id"],
                    "host": bridge["host"],
                    "port": 443,
                },
            }
        )

    # Fallback/добор: если split-пулы ещё не готовы или не хватает bypass-пар, добираем direct из общего пула.
    if len(servers_out) < RETURN_PAIRS:
        rows = _fetch_exits_least_loaded(db, limit=TOP_LEAST_LOADED, pool=None)
        chosen = _pick_best_tier_random(rows, k=RETURN_PAIRS)
        _append_direct_unique(servers_out, chosen, cap=RETURN_PAIRS)

    logger.info("edge_config: device_id=%s returned=%s", body.device_id, len(servers_out))
    return {"key": resolved_key, "servers": servers_out}
