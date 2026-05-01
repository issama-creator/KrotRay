from __future__ import annotations

import json
import os
import random
import socket
import time
from dataclasses import dataclass
from typing import Any

import redis


@dataclass
class RuntimeServer:
    server_id: str
    server_type: str
    count: float
    max_count: int
    status: str
    last_assigned: float
    host: str
    load: float


_REDIS_CLIENT: redis.Redis | None = None

_LUA_ASSIGN = """
redis.call('HINCRBYFLOAT', KEYS[1], 'count', ARGV[1])
redis.call('HSET', KEYS[1], 'last_assigned', ARGV[2])
return redis.call('HGET', KEYS[1], 'count')
"""

_LUA_DEASSIGN_CLAMP = """
local v = tonumber(redis.call('HINCRBYFLOAT', KEYS[1], 'count', ARGV[1]))
if v == nil then v = 0 end
if v < 0 then
  redis.call('HSET', KEYS[1], 'count', '0')
  return '0'
end
return tostring(v)
"""

_assign_script: Any | None = None
_deassign_script: Any | None = None


def get_redis() -> redis.Redis:
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT

    redis_url = (
        os.getenv("REDIS_URL", "").strip()
        or os.getenv("EDGE_REDIS_URL", "").strip()
        or "redis://127.0.0.1:6379/0"
    )
    _REDIS_CLIENT = redis.Redis.from_url(redis_url, decode_responses=True)
    return _REDIS_CLIENT


def _get_assign_script(client: redis.Redis):
    global _assign_script
    if _assign_script is None:
        _assign_script = client.register_script(_LUA_ASSIGN)
    return _assign_script


def _get_deassign_script(client: redis.Redis):
    global _deassign_script
    if _deassign_script is None:
        _deassign_script = client.register_script(_LUA_DEASSIGN_CLAMP)
    return _deassign_script


def load_server_ids(client: redis.Redis) -> list[str]:
    raw = client.get("servers:list")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(v) for v in parsed]


def _server_key(server_id: str) -> str:
    return f"server:{server_id}"


def load_server(client: redis.Redis, server_id: str) -> RuntimeServer | None:
    data = client.hgetall(_server_key(server_id))
    if not data:
        return None

    server_type = str(data.get("type", "")).strip().lower()
    if server_type not in {"wifi", "bypass"}:
        return None

    count = max(0.0, float(data.get("count", "0") or 0.0))
    max_count = max(1, int(float(data.get("max", "180") or 180)))
    status = str(data.get("status", "alive") or "alive").strip().lower()
    last_assigned = float(data.get("last_assigned", "0") or 0.0)
    host = str(data.get("host", "") or "").strip() or server_id
    load = count / max_count

    return RuntimeServer(
        server_id=server_id,
        server_type=server_type,
        count=count,
        max_count=max_count,
        status=status,
        last_assigned=last_assigned,
        host=host,
        load=load,
    )


def load_all_servers(client: redis.Redis) -> list[RuntimeServer]:
    out: list[RuntimeServer] = []
    for sid in load_server_ids(client):
        srv = load_server(client, sid)
        if srv is not None:
            out.append(srv)
    return out


def compute_weight(server: RuntimeServer, now_ts: float) -> float:
    load = server.load
    score = max(0.0, 1.0 - load)
    base = score**3
    penalty_recent = 0.8 if (now_ts - server.last_assigned) < 60 else 1.0
    penalty_hot = 0.3 if load > 0.8 else 1.0
    noise = random.uniform(0.9, 1.1)
    return max(0.0, base * penalty_recent * penalty_hot * noise)


def _weighted_pick_roulette(pool: list[dict[str, Any]], k: int) -> list[RuntimeServer]:
    """
    Roulette-wheel sampling without replacement (cumulative weights).
    Matches the intended distribution better than repeated random.choices on small pools.
    """
    selected: list[RuntimeServer] = []
    work = [{"srv": entry["srv"], "weight": float(entry["weight"])} for entry in pool]

    for _ in range(min(k, len(work))):
        thresholds: list[float] = []
        total = 0.0
        for item in work:
            total += max(0.0, item["weight"])
            thresholds.append(total)

        if total <= 0:
            break

        r = random.uniform(0.0, total)
        picked_idx = None
        for i, threshold in enumerate(thresholds):
            if r <= threshold:
                picked_idx = i
                break
        if picked_idx is None:
            picked_idx = len(work) - 1

        chosen = work.pop(picked_idx)
        selected.append(chosen["srv"])

    return selected


def _pick_from_group_once(
    servers: list[RuntimeServer],
    k: int,
    *,
    now_ts: float,
    cap_mult: float | None,
) -> list[dict[str, Any]]:
    filtered = [
        s
        for s in servers
        if s.status == "alive" and (cap_mult is None or s.count < (s.max_count * cap_mult))
    ]
    ranked = sorted(filtered, key=lambda s: s.load)[:20]
    pool_entries = [{"srv": s, "weight": compute_weight(s, now_ts)} for s in ranked]
    selected = _weighted_pick_roulette(pool_entries, k=k)

    if len(selected) < k:
        selected_ids = {s.server_id for s in selected}
        for srv in ranked:
            if srv.server_id not in selected_ids:
                selected.append(srv)
                selected_ids.add(srv.server_id)
                if len(selected) >= k:
                    break

    selected = sorted(selected[:k], key=lambda s: s.load)
    out: list[dict[str, Any]] = []
    for idx, srv in enumerate(selected, start=1):
        out.append({"id": srv.server_id, "type": srv.server_type, "priority": idx})
    return out


def pick_from_group(servers: list[RuntimeServer], k: int = 2) -> list[dict[str, Any]]:
    now_ts = time.time()
    # Tier 1: строгий порог на «переполнение». Tier 2: только alive (мягкий fallback).
    last: list[dict[str, Any]] = []
    for cap_mult in (1.2, None):
        out = _pick_from_group_once(servers, k, now_ts=now_ts, cap_mult=cap_mult)
        last = out
        if len(out) >= k:
            return out
    return last


def pick_servers_dual(servers: list[RuntimeServer]) -> list[dict[str, Any]]:
    wifi = [s for s in servers if s.server_type == "wifi"]
    bypass = [s for s in servers if s.server_type == "bypass"]
    alive_wifi_n = sum(1 for s in wifi if s.status == "alive")
    alive_bypass_n = sum(1 for s in bypass if s.status == "alive")
    if alive_wifi_n < 2 or alive_bypass_n < 2:
        raise ValueError("not enough alive servers per type (need >=2 wifi and >=2 bypass alive)")

    picked_wifi = pick_from_group(wifi, k=2)
    picked_bypass = pick_from_group(bypass, k=2)
    if len(picked_wifi) < 2 or len(picked_bypass) < 2:
        raise ValueError("selection produced incomplete quad after fallback tiers")

    combined = picked_wifi + picked_bypass
    used: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in combined:
        sid = str(item["id"])
        if sid in used:
            continue
        used.add(sid)
        unique.append(item)

    wifi_count = sum(1 for s in unique if s["type"] == "wifi")
    bypass_count = sum(1 for s in unique if s["type"] == "bypass")
    if len(unique) != 4 or wifi_count != 2 or bypass_count != 2:
        raise ValueError("failed to select 2 wifi + 2 bypass without duplicates")
    return unique


def user_assignment_redis_key(account_id: int) -> str:
    """Кэш назначения привязан к внутреннему users.id (стабилен после attach)."""
    return f"user:kf:{account_id}"


def invalidate_user_assignment(client: redis.Redis, account_id: int) -> None:
    client.delete(user_assignment_redis_key(account_id))


def get_cached_user(client: redis.Redis, account_id: int) -> dict[str, Any] | None:
    key = user_assignment_redis_key(account_id)
    data = client.hgetall(key)
    if not data:
        return None
    try:
        servers = json.loads(data.get("servers", "[]"))
    except json.JSONDecodeError:
        return None
    next_update = float(data.get("next_update", "0") or 0.0)
    return {"servers": servers, "next_update": next_update}


def save_cached_user(client: redis.Redis, account_id: int, servers: list[dict[str, Any]], next_update: float) -> None:
    key = user_assignment_redis_key(account_id)
    payload = {"servers": json.dumps(servers, separators=(",", ":")), "next_update": str(next_update)}
    pipe = client.pipeline()
    pipe.hset(key, mapping=payload)
    pipe.expire(key, 3 * 24 * 60 * 60)
    pipe.execute()


def apply_assign(client: redis.Redis, servers: list[dict[str, Any]], amount: float = 0.25) -> None:
    now_ts = str(time.time())
    script = _get_assign_script(client)
    amt = str(float(amount))
    for item in servers:
        sid = str(item["id"])
        key = _server_key(sid)
        script(keys=[key], args=[amt, now_ts])


def apply_deassign(client: redis.Redis, servers: list[dict[str, Any]], amount: float = 0.25) -> None:
    script = _get_deassign_script(client)
    amt = str(-float(amount))
    for item in servers:
        sid = str(item["id"])
        key = _server_key(sid)
        script(keys=[key], args=[amt])


def tcp_healthcheck(host: str, port: int, timeout_sec: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False
