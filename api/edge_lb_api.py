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
# Сколько exit берём в короткий список по нагрузке, из них случайно выбираем пары
TOP_EXITS = 8
PICK_EXITS = 4


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


@router.post("/config")
def post_edge_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    1) Все активные exit.
    2) Нагрузка = число edge_devices с last_seen в последних ONLINE_SEC секунд (только по exit server_id).
    3) Сортировка по нагрузке ASC, топ TOP_EXITS.
    4) Случайно PICK_EXITS exit.
    5) Для каждого — bridge с тем же group_id (is_active).
    """
    # Нагрузка только по exit: считаем устройства, привязанные к этому exit id
    rows = db.execute(
        text(
            """
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
            ORDER BY load ASC, s.id ASC
            LIMIT :top_n
            """
        ),
        {"online_sec": ONLINE_SEC, "top_n": TOP_EXITS},
    ).mappings().all()

    if not rows:
        return {"servers": []}

    # Случайность среди наименее загруженных (anti-spike)
    k = min(PICK_EXITS, len(rows))
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
