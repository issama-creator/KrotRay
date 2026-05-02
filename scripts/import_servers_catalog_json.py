"""
Импорт каталога серверов в Postgres (потом залейте в Redis: scripts/init_redis_servers.py).

Формат JSON — массив объектов:

  [
    {"name": "EU1", "host": "10.0.0.1", "grpc_port": 8080, "type": "wifi", "region": "eu", "max_users": 180},
    {"name": "RU1", "host": "10.0.0.2", "grpc_port": 8080, "type": "bypass", "region": "ru", "link_to_host": "10.0.0.1"}
  ]

Правила:
- Сначала обрабатываются все type=wifi (в порядке массива), затем bypass.
- Для bypass поле link_to_host должно совпадать с host уже добавленного wifi-сервера.
- plan опционально (по умолчанию default).

Пример:
  python scripts/import_servers_catalog_json.py servers.catalog.json
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
    p = argparse.ArgumentParser(description="Import key-factory server rows into Postgres")
    p.add_argument("json_path", type=str, help="Путь к JSON-массиву серверов")
    args = p.parse_args()

    path = args.json_path
    if not os.path.isfile(path):
        print(f"Файл не найден: {path}", file=sys.stderr)
        return 2

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or not data:
        print("Ожидается непустой JSON-массив [...]", file=sys.stderr)
        return 2

    from db.models.server import Server
    from db.session import SessionLocal

    wifi_rows = [r for r in data if isinstance(r, dict) and str(r.get("type", "")).lower() == "wifi"]
    bypass_rows = [r for r in data if isinstance(r, dict) and str(r.get("type", "")).lower() == "bypass"]
    if not wifi_rows or not bypass_rows:
        print("Нужны и wifi, и bypass записи в JSON.", file=sys.stderr)
        return 2

    db = SessionLocal()
    host_to_id: dict[str, int] = {}
    try:
        for i, row in enumerate(wifi_rows):
            name = str(row.get("name", "")).strip()
            host = str(row.get("host", "")).strip()
            if not name or not host:
                print(f"wifi[{i}]: нужны name и host", file=sys.stderr)
                return 2
            grpc_port = int(row.get("grpc_port", 8080))
            max_users = int(row.get("max_users", 180))
            region = (row.get("region") and str(row.get("region"))) or None
            plan = str(row.get("plan", "default")).strip() or "default"
            s = Server(
                name=name,
                host=host,
                grpc_port=grpc_port,
                active_users=0,
                max_users=max_users,
                enabled=True,
                kf_type="wifi",
                region=region,
                linked_server_id=None,
                plan=plan,
            )
            db.add(s)
            db.flush()
            host_to_id[host] = s.id

        for i, row in enumerate(bypass_rows):
            name = str(row.get("name", "")).strip()
            host = str(row.get("host", "")).strip()
            link_host = str(row.get("link_to_host", "")).strip()
            if not name or not host or not link_host:
                print(f"bypass[{i}]: нужны name, host, link_to_host", file=sys.stderr)
                return 2
            lid = host_to_id.get(link_host)
            if lid is None:
                print(
                    f"bypass[{i}]: link_to_host={link_host!r} не найден среди wifi host в этом файле",
                    file=sys.stderr,
                )
                return 2
            grpc_port = int(row.get("grpc_port", 8080))
            max_users = int(row.get("max_users", 180))
            region = (row.get("region") and str(row.get("region"))) or None
            plan = str(row.get("plan", "default")).strip() or "default"
            db.add(
                Server(
                    name=name,
                    host=host,
                    grpc_port=grpc_port,
                    active_users=0,
                    max_users=max_users,
                    enabled=True,
                    kf_type="bypass",
                    region=region,
                    linked_server_id=lid,
                    plan=plan,
                )
            )

        db.commit()
        print(f"OK: добавлено wifi={len(wifi_rows)} bypass={len(bypass_rows)}. Запустите: python scripts/init_redis_servers.py")
        return 0
    except Exception as e:
        db.rollback()
        print(e, file=sys.stderr)
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
