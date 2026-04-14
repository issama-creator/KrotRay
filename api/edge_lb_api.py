"""
Ядро: heartbeat по exit, нагрузка только по exit, выдача 4 пар bridge+exit.

Таблицы: edge_servers, edge_devices (не legacy servers / не CP devices).
Эндпоинты: POST /ping, POST /config (рядом с GET /config из cp_api — другой HTTP-метод).
"""
from __future__ import annotations

import logging
import random
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cp_api import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["edge-lb"])

# Окно «онлайн» для учёта нагрузки на exit (только свежие last_seen)
ONLINE_SEC = 90
# Exit с нагрузкой > этого числа новым клиентам не отдаём (перегруз).
MAX_EXIT_LOAD_FOR_ASSIGNMENT = 150
# Среди «доступных» exit: топ наименее загруженных, затем random → финальные пары.
TOP_LEAST_LOADED = 10
RETURN_PAIRS = 4


class PingBody(BaseModel):
    device_id: str = Field(..., min_length=1)
    server_id: int = Field(..., description="id exit-сервера (type=exit)")


@router.post("/ping")
def post_ping(body: PingBody, db: Session = Depends(get_db)) -> dict[str, bool]:
    """
    Heartbeat: одна строка на device_id (upsert).
    server_id — только exit; нагрузка считается по привязке устройства к exit.
    """
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
        {"device_id": body.device_id.strip(), "server_id": body.server_id},
    )
    db.commit()
    return {"ok": True}


def _fetch_exits_least_loaded(
    db: Session,
    *,
    max_load: int | None,
    limit: int,
) -> list[Any]:
    """
    Активные exit с подсчётом load (онлайн-устройства за ONLINE_SEC).
    Если max_load задан — только exit с load <= max_load (сверх порога «не выдаём»).
    """
    load_filter = ""
    params: dict[str, Any] = {"online_sec": ONLINE_SEC, "top_n": limit}
    if max_load is not None:
        load_filter = "AND COALESCE(cnt.c, 0) <= :max_load"
        params["max_load"] = max_load

    sql = f"""
            SELECT
                s.id,
                s.name,
                s.group_id,
                s.host,
                s.real_ip,
                COALESCE(cnt.c, 0)::int AS load
            FROM edge_servers s
            LEFT JOIN (
                SELECT d.server_id, COUNT(*)::int AS c
                FROM edge_devices d
                WHERE d.last_seen > NOW() - (:online_sec * INTERVAL '1 second')
                GROUP BY d.server_id
            ) cnt ON cnt.server_id = s.id
            WHERE s.type = 'exit' AND s.is_active = true
            {load_filter}
            ORDER BY load ASC, s.id ASC
            LIMIT :top_n
            """
    return list(db.execute(text(sql), params).mappings().all())


@router.post("/config")
def post_edge_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    1) Нагрузка только по exit (COUNT edge_devices с last_seen за ONLINE_SEC).
    2) Не отдаём exit с load > MAX_EXIT_LOAD_FOR_ASSIGNMENT (перегруженные).
    3) Из оставшихся — топ TOP_LEAST_LOADED наименее загруженных.
    4) random.sample до RETURN_PAIRS — размазать наплыв.
    5) К каждому exit — активный bridge с тем же group_id.
    Если все exit > порога — fallback: топ TOP_LEAST_LOADED без фильтра по load (сервис не пустой).
    """
    rows = _fetch_exits_least_loaded(
        db,
        max_load=MAX_EXIT_LOAD_FOR_ASSIGNMENT,
        limit=TOP_LEAST_LOADED,
    )
    if not rows:
        # Все перегружены выше порога — всё равно отдаём наименее жирные TOP_LEAST_LOADED
        rows = _fetch_exits_least_loaded(db, max_load=None, limit=TOP_LEAST_LOADED)

    if not rows:
        return {"servers": []}

    # Случайные RETURN_PAIRS из топ-10 наименее загруженных (anti-spike)
    k = min(RETURN_PAIRS, len(rows))
    chosen = random.sample(list(rows), k=k)

    servers_out: list[dict[str, Any]] = []
    for ex in chosen:
        gid = ex["group_id"]
        if gid is None:
            logger.warning("edge_config: exit id=%s has no group_id, skip", ex["id"])
            continue

        br = db.execute(
            text(
                """
                SELECT id, host
                FROM edge_servers
                WHERE type = 'bridge' AND is_active = true AND group_id = :gid
                ORDER BY id ASC
                LIMIT 1
                """
            ),
            {"gid": gid},
        ).mappings().first()

        if br is None:
            logger.warning("edge_config: no active bridge for group_id=%s (exit id=%s)", gid, ex["id"])
            continue

        servers_out.append(
            {
                "exit": {
                    "id": ex["id"],
                    "host": ex["host"],
                },
                "bridge": {
                    "id": br["id"],
                    "host": br["host"],
                },
            }
        )

        logger.info(
            "edge_config pick: exit_id=%s load=%s bridge_id=%s group_id=%s",
            ex["id"],
            ex["load"],
            br["id"],
            gid,
        )

    return {"servers": servers_out}
