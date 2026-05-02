"""
Добавляет в Postgres пачку серверов для key-factory (kf_type wifi | bypass).

По умолчанию: 10 строк — 5× wifi + 5× bypass — чтобы после init_redis_servers.py
балансировщик имел ≥2 узлов каждого типа (у тебя уже может быть id=1 wifi).

Запуск из корня репозитория:
  cd /opt/krotray && source venv/bin/activate
  python scripts/seed_kf_servers_bulk.py
  python scripts/seed_kf_servers_bulk.py --dry-run

Потом перезалить Redis:
  python scripts/init_redis_servers.py

Подстрой хосты под реальные машины: либо правь константы ниже, либо передай --host-prefix.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# --- правь под свою сеть / заглушки ---
DEFAULT_HOST_PREFIX = "103.137.251"  # хосты будут .166 … .175 при дефолтном старте
DEFAULT_LAST_OCTET_START = 166
DEFAULT_GRPC_PORT = 8081


def _build_rows(
    *,
    wifi_n: int,
    bypass_n: int,
    host_prefix: str,
    last_octet_start: int,
    grpc_port: int,
    name_prefix: str,
) -> list[dict]:
    rows: list[dict] = []
    octet = last_octet_start
    for i in range(wifi_n):
        rows.append(
            {
                "name": f"{name_prefix}-wifi-{i + 1:02d}",
                "host": f"{host_prefix}.{octet}",
                "grpc_port": grpc_port,
                "kf_type": "wifi",
                "region": "eu",
                "enabled": True,
            },
        )
        octet += 1
    for i in range(bypass_n):
        rows.append(
            {
                "name": f"{name_prefix}-bypass-{i + 1:02d}",
                "host": f"{host_prefix}.{octet}",
                "grpc_port": grpc_port,
                "kf_type": "bypass",
                "region": "ru",
                "enabled": True,
            },
        )
        octet += 1
    return rows


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="INSERT servers для key-factory (wifi + bypass)")
    p.add_argument("--wifi", type=int, default=5, help="сколько строк с kf_type=wifi")
    p.add_argument("--bypass", type=int, default=5, help="сколько строк с kf_type=bypass")
    p.add_argument(
        "--host-prefix",
        default=DEFAULT_HOST_PREFIX,
        help=f"первые три октета IPv4, например 103.137.251 (default: {DEFAULT_HOST_PREFIX})",
    )
    p.add_argument(
        "--octet-start",
        type=int,
        default=DEFAULT_LAST_OCTET_START,
        help=f"последний октет первого хоста (default: {DEFAULT_LAST_OCTET_START})",
    )
    p.add_argument("--grpc-port", type=int, default=DEFAULT_GRPC_PORT)
    p.add_argument("--name-prefix", default="kf", help="префикс имени строки в servers.name")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    from db.models.server import Server
    from db.session import SessionLocal

    specs = _build_rows(
        wifi_n=args.wifi,
        bypass_n=args.bypass,
        host_prefix=args.host_prefix.strip(),
        last_octet_start=args.octet_start,
        grpc_port=args.grpc_port,
        name_prefix=args.name_prefix.strip() or "kf",
    )

    print(f"Будет добавлено {len(specs)} сервер(ов):")
    for s in specs:
        print(f"  {s['name']:24} {s['kf_type']:8} {s['host']}:{s['grpc_port']} region={s['region']}")

    if args.dry_run:
        print("(dry-run — INSERT не выполняется)")
        return 0

    db = SessionLocal()
    try:
        for s in specs:
            db.add(
                Server(
                    name=s["name"],
                    host=s["host"],
                    grpc_port=s["grpc_port"],
                    enabled=s["enabled"],
                    kf_type=s["kf_type"],
                    region=s["region"],
                ),
            )
        db.commit()
        print("OK: INSERT выполнен. Запусти: python scripts/init_redis_servers.py")
        return 0
    except Exception as e:
        db.rollback()
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
