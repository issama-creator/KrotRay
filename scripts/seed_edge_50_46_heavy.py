#!/usr/bin/env python3
"""
Сценарий для проверки POST /config (порог: выдаём только exit с онлайн-нагрузкой < 150).

- 50 пар exit + bridge (group_id g001..g050)
- первые 46 exit: ровно 150 онлайн-устройств (не выдаются, load >= 150)
- последние 4 exit: нагрузки 140, 130, 115, 90 (все < 150 — только они в пуле)

Запуск:
  cd /opt/krotray && source venv/bin/activate
  export $(grep -v '^#' .env | xargs)
  python scripts/seed_edge_50_46_heavy.py --yes

Проверка:
  curl -s -X POST http://127.0.0.1:8000/config -H "Content-Type: application/json" -d "{}" | python3 -m json.tool
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine, text

# Соответствует edge_lb_api.MAX_EXIT_ONLINE_EXCLUSIVE = 150 (load < 150)
HEAVY_ONLINE = 150
LIGHT_LOADS = (140, 130, 115, 90)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--yes",
        action="store_true",
        help="обязательно: TRUNCATE edge_servers CASCADE",
    )
    args = p.parse_args()
    if not args.yes:
        print("Добавь флаг --yes (очистит edge_*).", file=sys.stderr)
        return 1

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("Нужен DATABASE_URL", file=sys.stderr)
        return 1

    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE TABLE edge_servers RESTART IDENTITY CASCADE"))

        for i in range(1, 51):
            gid = f"g{i:03d}"
            conn.execute(
                text(
                    """
                    INSERT INTO edge_servers (name, type, group_id, host, real_ip, is_active)
                    VALUES (:ename, 'exit', :gid, :ehost, :eip, true)
                    """
                ),
                {
                    "ename": f"exit-{i}",
                    "gid": gid,
                    "ehost": f"exit{i}.test",
                    "eip": f"10.0.{i % 200}.1",
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO edge_servers (name, type, group_id, host, real_ip, is_active)
                    VALUES (:bname, 'bridge', :gid, :bhost, :bip, true)
                    """
                ),
                {
                    "bname": f"bridge-{i}",
                    "gid": gid,
                    "bhost": f"bridge{i}.test",
                    "bip": f"10.1.{i % 200}.1",
                },
            )

        heavy_ids = list(
            conn.execute(
                text("SELECT id FROM edge_servers WHERE type = 'exit' ORDER BY id ASC LIMIT 46")
            ).scalars().all()
        )

        for sid in heavy_ids:
            conn.execute(
                text(
                    """
                    INSERT INTO edge_devices (device_id, server_id, last_seen)
                    SELECT gen_random_uuid()::text, :sid, NOW()
                    FROM generate_series(1, :n)
                    """
                ),
                {"sid": sid, "n": HEAVY_ONLINE},
            )

        light_rows = list(
            conn.execute(
                text(
                    """
                    SELECT id, name FROM edge_servers
                    WHERE type = 'exit'
                    ORDER BY id ASC
                    OFFSET 46 LIMIT 4
                    """
                )
            ).all()
        )

        if len(light_rows) != len(LIGHT_LOADS):
            print(f"Ожидалось 4 лёгких exit, получено {len(light_rows)}", file=sys.stderr)
            return 1

        for (sid, name), n in zip(light_rows, LIGHT_LOADS, strict=True):
            conn.execute(
                text(
                    """
                    INSERT INTO edge_devices (device_id, server_id, last_seen)
                    SELECT gen_random_uuid()::text, :sid, NOW()
                    FROM generate_series(1, :n)
                    """
                ),
                {"sid": sid, "n": n},
            )

    print("Готово.")
    print(f"  «Забитые» exit (онлайн={HEAVY_ONLINE}, не выдаются): {len(heavy_ids)} шт.")
    print("  Лёгкие exit (онлайн < 150):")
    for (sid, name), n in zip(light_rows, LIGHT_LOADS, strict=True):
        print(f"    id={sid} {name} → load={n}")
    print("Ожидание: POST /config — только эти 4 exit (порядок в JSON может меняться из-за random).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
