"""
Каталог key-factory: Postgres (источник правды) → Redis (runtime для minimal_lb).

Условие строки в синке:
  servers.enabled = true  AND  servers.kf_type IN ('wifi','bypass')

В Redis только контракт балансировщика (без region, linked_server_id, plan и т.д.):
  servers:list          → JSON-массив id (строки, совпадают с servers.id в Postgres)
  server:{id}           → hash: type, host, max, count, status, last_assigned

Перед записью полностью очищаются старый servers:list и все ключи server:*.

Использование:
  python scripts/init_redis_servers.py
  python scripts/init_redis_servers.py --dry-run

Сопоставление полей Postgres ↔ промпт / Redis:
  kf_type      → redis hash field ``type`` (wifi | bypass)
  enabled      → фильтр ``is_active`` из ТЗ (в БД колонка ``enabled``)
  host + grpc_port → одно поле ``host`` в Redis (если host уже содержит ':', не дописываем порт)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> None:
        """Без пакета python-dotenv: задайте окружение в shell (например ``set -a && source .env && set +a``)."""

# Фиксированный потолок слотов в Redis для LB (не храним count в Postgres).
REDIS_MAX_DEFAULT = 180


def _redis_runtime_host(host: str, grpc_port: int, server_id: int) -> str:
    base = (host or "").strip()
    if not base:
        return str(server_id)
    if ":" in base:
        return base
    return f"{base}:{int(grpc_port)}"


def _flush_redis_catalog(r) -> None:
    """Удалить servers:list и все server:*."""
    keys = list(r.scan_iter(match="server:*"))
    if keys:
        r.delete(*keys)
    r.delete("servers:list")


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Postgres servers → Redis key-factory catalog (полная перезапись)")
    p.add_argument("--dry-run", action="store_true", help="Только печать плана, без Redis")
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
            .order_by(Server.id),
        ).all()
    finally:
        db.close()

    if not rows:
        print(
            "Нет строк с kf_type wifi|bypass и enabled=true. "
            "Заполни каталог в Postgres (поля kf_type, host, enabled; опционально region, linked_server_id).",
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
            "host": _redis_runtime_host(s.host, s.grpc_port, s.id),
            "max": str(REDIS_MAX_DEFAULT),
            "count": "0",
            "status": "alive",
            "last_assigned": "0",
        }
        payloads.append((sid, mapping))

    print(f"Запись каталога: {len(ids)} сервер(ов), redis_url={redis_url!r}")
    for sid, m in payloads:
        print(f"  server:{sid} type={m['type']} host={m['host']} max={m['max']}")

    if args.dry_run:
        print("(dry-run: очистка Redis и запись не выполняются)")
        return 0

    r = redis.Redis.from_url(redis_url, decode_responses=True)
    _flush_redis_catalog(r)

    pipe = r.pipeline(transaction=True)
    for sid, mapping in payloads:
        pipe.hset(f"server:{sid}", mapping=mapping)
    pipe.set("servers:list", json.dumps(ids, separators=(",", ":")))
    pipe.execute()

    print("OK: Redis очищен и заново заполнен (servers:list + server:{id}, count=0, max=180).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
