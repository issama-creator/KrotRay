from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

EDGE_TOP_CACHE_KEY = os.getenv("EDGE_TOP_CACHE_KEY", "edge:top:candidates:v1")
EDGE_TOP_CACHE_TTL_SEC = int(os.getenv("EDGE_TOP_CACHE_TTL_SEC", "30"))
TOP_LEAST_LOADED = int(os.getenv("EDGE_TOP_LEAST_LOADED", "50"))
EDGE_POOL_DIRECT = os.getenv("EDGE_POOL_DIRECT", "nl")
EDGE_POOL_BYPASS = os.getenv("EDGE_POOL_BYPASS", "bypass")
EDGE_POOL_SHARED = os.getenv("EDGE_POOL_SHARED", "shared")
EDGE_LOAD_TIE_BREAK = os.getenv("EDGE_LOAD_TIE_BREAK", "random").strip().lower()

_redis_client = None
_redis_import_error = False


def _get_redis_client():
    global _redis_client, _redis_import_error
    if _redis_import_error:
        return None
    if _redis_client is not None:
        return _redis_client

    redis_url = os.getenv("EDGE_REDIS_URL", "").strip()
    if not redis_url:
        return None
    try:
        import redis

        _redis_client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        return _redis_client
    except Exception:
        _redis_import_error = True
        logger.exception("edge_top_cache: redis client unavailable")
        return None


def load_top_candidates() -> dict[str, Any] | None:
    client = _get_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(EDGE_TOP_CACHE_KEY)
        if not raw:
            return None
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        return payload
    except Exception:
        logger.exception("edge_top_cache: failed to load cache")
        return None


def save_top_candidates(payload: dict[str, Any]) -> bool:
    client = _get_redis_client()
    if client is None:
        return False
    try:
        client.setex(EDGE_TOP_CACHE_KEY, EDGE_TOP_CACHE_TTL_SEC, json.dumps(payload, separators=(",", ":")))
        return True
    except Exception:
        logger.exception("edge_top_cache: failed to save cache")
        return False


def _fetch_exits_least_loaded_split(db: Session, *, limit: int) -> tuple[list[Any], list[Any]]:
    tie_break_order = "RANDOM()" if EDGE_LOAD_TIE_BREAK == "random" else "s.id ASC"
    sql = """
        WITH load_by_server AS (
            SELECT d.server_id, COUNT(*)::int AS c
            FROM edge_devices d
            WHERE d.last_seen > NOW() - (:online_sec * INTERVAL '1 second')
            GROUP BY d.server_id
        ),
        ranked AS (
            SELECT
                s.id,
                s.name,
                s.host,
                s.group_id,
                COALESCE(s.pool, :shared_pool) AS pool,
                COALESCE(l.c, 0)::int AS load,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(s.pool, :shared_pool)
                    ORDER BY COALESCE(l.c, 0) ASC, __TIE_BREAK__
                ) AS rn
            FROM edge_servers s
            LEFT JOIN load_by_server l ON l.server_id = s.id
            WHERE s.type = 'exit'
              AND s.is_active = true
              AND COALESCE(s.pool, :shared_pool) IN (:direct_pool, :bypass_pool)
        )
        SELECT id, name, host, group_id, pool, load
        FROM ranked
        WHERE rn <= :top_n
        ORDER BY pool ASC, load ASC, id ASC
    """
    sql = sql.replace("__TIE_BREAK__", tie_break_order)
    # Keep ONLINE_SEC consistent with existing edge /config SQL logic.
    online_sec = int(os.getenv("EDGE_ONLINE_SEC", "180"))
    rows = list(
        db.execute(
            text(sql),
            {
                "online_sec": online_sec,
                "top_n": limit,
                "shared_pool": EDGE_POOL_SHARED,
                "direct_pool": EDGE_POOL_DIRECT,
                "bypass_pool": EDGE_POOL_BYPASS,
            },
        )
        .mappings()
        .all()
    )
    direct_rows = [r for r in rows if str(r["pool"]) == EDGE_POOL_DIRECT]
    bypass_rows = [r for r in rows if str(r["pool"]) == EDGE_POOL_BYPASS]
    return direct_rows, bypass_rows


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


def build_top_candidates_payload(db: Session) -> dict[str, Any]:
    direct_rows, bypass_rows = _fetch_exits_least_loaded_split(db, limit=TOP_LEAST_LOADED)
    direct_candidates: list[dict[str, Any]] = [
        {
            "id": int(ex["id"]),
            "host": ex["host"],
            "port": 443,
            "mode": "direct",
            "pool": ex["pool"],
            "load": int(ex.get("load") or 0),
        }
        for ex in direct_rows
    ]

    bypass_group_ids = [str(ex["group_id"]) for ex in bypass_rows if ex.get("group_id")]
    bridges_by_group = _fetch_bridges_by_group(db, group_ids=bypass_group_ids, pool=EDGE_POOL_BYPASS)
    bypass_candidates: list[dict[str, Any]] = []
    for ex in bypass_rows:
        gid = str(ex.get("group_id") or "")
        bridge = bridges_by_group.get(gid)
        if not bridge:
            continue
        bypass_candidates.append(
            {
                "id": int(ex["id"]),
                "host": ex["host"],
                "port": 443,
                "mode": "bypass",
                "pool": ex["pool"],
                "load": int(ex.get("load") or 0),
                "bridge": {
                    "id": int(bridge["id"]),
                    "host": bridge["host"],
                    "port": 443,
                },
            }
        )

    return {
        "direct": direct_candidates,
        "bypass": bypass_candidates,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

