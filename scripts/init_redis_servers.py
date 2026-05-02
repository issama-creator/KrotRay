"""
Залить каталог key-factory из Postgres в Redis (runtime для minimal_lb).

Условие попадания в Redis: servers.kf_type IN ('wifi','bypass') AND servers.enabled.

Redis ключ ноды: server:<postgres_servers.id> — id совпадает с PK в БД.
Поля hash (без изменения контракта балансировщика): type, host, max, count, status, last_assigned.

Связка RU→EU (linked_server_id) хранится только в Postgres; в Redis не дублируется.

Пример:
  python scripts/init_redis_servers.py
  python scripts/init_redis_servers.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Postgres servers → Redis key-factory catalog")
    p.add_argument("--dry-run", action="store_true", help="Только печать, без записи в Redis")
    args = p.parse_args()

    redis_url = (
        os.getenv("REDIS_URL", "").strip()
        or os.getenv("EDGE_REDIS_URL", "").strip()
        or "redis://127.0.0.1:6379/0"
    )
    try:
        import redis
    except ImportError:
        print("pip install redis", file=sys.stderr)
        return 2

    from sqlalchemy import select

    from db.models.server import Server
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(Server)
            .where(Server.kf_type.in_(["wifi", "bypass"]))
            .where(Server.enabled.is_(True))
            .order_by(Server.id)
        ).all()
    finally:
        db.close()

    if not rows:
        print(
            "Нет строк с kf_type wifi|bypass и enabled=true. "
            "Добавьте серверы в Postgres или выполните scripts/import_servers_catalog_json.py",
            file=sys.stderr,
        )
        return 2

    ids = [str(s.id) for s in rows]
    payloads: list[tuple[str, dict[str, str]]] = []
    for s in rows:
        sid = str(s.id)
        ktype = (s.kf_type or "").strip().lower()
        mapping = {
            "type": ktype,
            "host": s.host.strip(),
            "max": str(max(1, int(s.max_users or 100))),
            "count": "0",
            "status": "alive",
            "last_assigned": "0",
        }
        payloads.append((sid, mapping))

    print(f"Будет записано серверов: {len(ids)} redis_url={redis_url!r}")
    for sid, m in payloads:
        print(f"  server:{sid} type={m['type']} host={m['host']} max={m['max']}")

    if args.dry_run:
        print("(dry-run, Redis не трогаем)")
        return 0

    r = redis.Redis.from_url(redis_url, decode_responses=True)
    for sid, mapping in payloads:
        r.hset(f"server:{sid}", mapping=mapping)
    r.set("servers:list", json.dumps(ids, separators=(",", ":")))
    print("OK: servers:list и server:{id} обновлены, count сброшен в 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
