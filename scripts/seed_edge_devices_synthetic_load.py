#!/usr/bin/env python3
"""
Синтетическая нагрузка на exit через edge_devices (last_seen = NOW(), попадает в окно ONLINE_SEC).

Не трогает edge_servers. Удаляет только свои строки: device_id LIKE 'synth-load-%'.

Пример (последние 4 exit — по 5 устройств, остальные exit — по 150):
  set DATABASE_URL=postgresql://...
  python scripts/seed_edge_devices_synthetic_load.py --yes

Проверка распределения в psql — см. комментарий в конце main().
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine, text


def main() -> int:
    p = argparse.ArgumentParser(
        description="Засеять edge_devices для теста least-loaded /config (без TRUNCATE edge_servers)."
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="обязательно: удалит synth-load-* и вставит новые строки",
    )
    p.add_argument(
        "--per-exit",
        type=int,
        default=150,
        help="сколько синтетических устройств на каждый «тяжёлый» exit (по умолчанию 150)",
    )
    p.add_argument(
        "--reserve-exits",
        type=int,
        default=4,
        help="сколько exit с конца списка (по id) оставить «лёгкими»",
    )
    p.add_argument(
        "--reserve-load",
        type=int,
        default=5,
        help="сколько устройств на каждый лёгкий exit (по умолчанию 5)",
    )
    args = p.parse_args()
    if not args.yes:
        print("Добавь флаг --yes (удалит device_id LIKE 'synth-load%%' и вставит данные).", file=sys.stderr)
        return 1

    url = os.environ.get("DATABASE_URL")
    if not url or not url.startswith("postgresql"):
        print("Нужен DATABASE_URL на PostgreSQL.", file=sys.stderr)
        return 1

    per = max(0, int(args.per_exit))
    reserve_exits = max(0, int(args.reserve_exits))
    reserve_load = max(0, int(args.reserve_load))

    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM edge_devices WHERE device_id LIKE 'synth-load-%'"))

        exits = list(
            conn.execute(
                text(
                    """
                    SELECT id FROM edge_servers
                    WHERE type = 'exit' AND is_active = true
                    ORDER BY id ASC
                    """
                )
            ).scalars().all()
        )

        if not exits:
            print("Нет активных exit в edge_servers.", file=sys.stderr)
            return 1

        if reserve_exits >= len(exits):
            print("reserve-exits должно быть меньше числа exit.", file=sys.stderr)
            return 1

        heavy_ids = exits[:-reserve_exits] if reserve_exits else exits
        light_ids = exits[-reserve_exits:] if reserve_exits else []

        for sid in heavy_ids:
            conn.execute(
                text(
                    """
                    INSERT INTO edge_devices (device_id, server_id, last_seen)
                    SELECT 'synth-load-' || CAST(:sid AS TEXT) || '-' || CAST(gs AS TEXT), :sid, NOW()
                    FROM generate_series(1, :n) AS gs
                    ON CONFLICT (device_id) DO UPDATE SET
                        server_id = EXCLUDED.server_id,
                        last_seen = EXCLUDED.last_seen
                    """
                ),
                {"sid": sid, "n": per},
            )

        for sid in light_ids:
            if reserve_load <= 0:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO edge_devices (device_id, server_id, last_seen)
                    SELECT 'synth-load-' || CAST(:sid AS TEXT) || '-' || CAST(gs AS TEXT), :sid, NOW()
                    FROM generate_series(1, :n) AS gs
                    ON CONFLICT (device_id) DO UPDATE SET
                        server_id = EXCLUDED.server_id,
                        last_seen = EXCLUDED.last_seen
                    """
                ),
                {"sid": sid, "n": reserve_load},
            )

    print("Готово.")
    print(f"  Тяжёлых exit: {len(heavy_ids)} × {per} устройств (synth-load-*)")
    print(f"  Лёгких exit: {len(light_ids)} × {reserve_load} устройств (id: {light_ids})")
    print("  Очистка: DELETE FROM edge_devices WHERE device_id LIKE 'synth-load-%';")
    return 0


if __name__ == "__main__":
    sys.exit(main())
