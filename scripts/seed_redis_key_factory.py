"""
Заполнить Redis каталог серверов для key-factory.

Пример JSON (--from-json):

{
  "servers": [
    {"id": "w1", "type": "wifi", "host": "10.0.0.1", "max": 180},
    {"id": "w2", "type": "wifi", "host": "10.0.0.2", "max": 180},
    {"id": "b1", "type": "bypass", "host": "10.0.0.3", "max": 180},
    {"id": "b2", "type": "bypass", "host": "10.0.0.4", "max": 180}
  ]
}

Поля hash server:{id}: type, max, count (0), status (alive), last_assigned (0), host.
Также пишет servers:list как JSON массив id (порядок сохраняется).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Seed Redis servers for key factory balancer")
    p.add_argument(
        "--from-json",
        type=str,
        required=True,
        help="Путь к JSON с ключом servers: массив объектов id,type,host,max",
    )
    args = p.parse_args()

    path = args.from_json
    if not os.path.isfile(path):
        print(f"File not found: {path}", file=sys.stderr)
        return 2

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    servers = data.get("servers")
    if not isinstance(servers, list) or not servers:
        print("JSON must contain non-empty servers: [...]", file=sys.stderr)
        return 2

    redis_url = (
        os.getenv("REDIS_URL", "").strip() or os.getenv("EDGE_REDIS_URL", "").strip() or "redis://127.0.0.1:6379/0"
    )
    try:
        import redis
    except ImportError:
        print("pip install redis", file=sys.stderr)
        return 2

    r = redis.Redis.from_url(redis_url, decode_responses=True)

    ids: list[str] = []
    for i, row in enumerate(servers):
        if not isinstance(row, dict):
            print(f"servers[{i}] must be object", file=sys.stderr)
            return 2
        sid = str(row.get("id", "")).strip()
        stype = str(row.get("type", "")).strip().lower()
        host = str(row.get("host", "")).strip()
        mx = int(row.get("max", 180))
        if not sid or stype not in {"wifi", "bypass"} or not host or mx <= 0:
            print(f"Invalid row {i}: need id, type wifi|bypass, host, max>0 — got {row}", file=sys.stderr)
            return 2
        ids.append(sid)
        key = f"server:{sid}"
        r.hset(
            key,
            mapping={
                "type": stype,
                "host": host,
                "max": str(mx),
                "count": str(float(row.get("count", 0) or 0)),
                "status": str(row.get("status", "alive")),
                "last_assigned": str(float(row.get("last_assigned", 0) or 0)),
            },
        )

    r.set("servers:list", json.dumps(ids, separators=(",", ":")))
    print(f"OK: redis_url={redis_url!r} servers={len(ids)} list written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
