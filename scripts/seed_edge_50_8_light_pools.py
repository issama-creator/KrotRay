#!/usr/bin/env python3
"""
Чистит Edge и заливает 50 пар exit+bridge (как в старом сиде), но с пулами:

- exit 1–4:   pool=nl,     нагрузка 5 устройств  (лёгкие для direct)
- exit 5–8:   pool=bypass, нагрузка 5           (лёгкие для bypass)
- exit 9–29:  pool=nl,     нагрузка 150         (тяжёлые nl)
- exit 30–50: pool=bypass, нагрузка 150         (тяжёлые bypass)

Мосты: тот же group_id; pool у bridge совпадает с exit (для bypass-цепочки).

Запуск:
  source venv/bin/activate
  export DATABASE_URL='postgresql://...'
  python scripts/seed_edge_50_8_light_pools.py --yes

Очистка: TRUNCATE edge_servers CASCADE; TRUNCATE edge_users RESTART IDENTITY;
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine, text

HEAVY = 150
LIGHT = 5
PAIRS = 50


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--yes",
        action="store_true",
        help="TRUNCATE edge_servers + edge_users",
    )
    args = p.parse_args()
    if not args.yes:
        print("Добавь флаг --yes.", file=sys.stderr)
        return 1

    url = os.environ.get("DATABASE_URL")
    if not url or not url.startswith("postgresql"):
        print("Нужен DATABASE_URL (PostgreSQL).", file=sys.stderr)
        return 1

    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE TABLE edge_users RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE TABLE edge_servers RESTART IDENTITY CASCADE"))

        for i in range(1, PAIRS + 1):
            gid = f"g{i:03d}"
            if i <= 4:
                epool, bpool = "nl", "nl"
            elif i <= 8:
                epool, bpool = "bypass", "bypass"
            elif i <= 29:
                epool, bpool = "nl", "nl"
            else:
                epool, bpool = "bypass", "bypass"

            conn.execute(
                text(
                    """
                    INSERT INTO edge_servers (name, type, group_id, host, real_ip, is_active, pool)
                    VALUES (:ename, 'exit', :gid, :ehost, :eip, true, :epool)
                    """
                ),
                {
                    "ename": f"exit-{i}",
                    "gid": gid,
                    "ehost": f"exit{i}.test",
                    "eip": f"10.0.{i % 200}.1",
                    "epool": epool,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO edge_servers (name, type, group_id, host, real_ip, is_active, pool)
                    VALUES (:bname, 'bridge', :gid, :bhost, :bip, true, :bpool)
                    """
                ),
                {
                    "bname": f"bridge-{i}",
                    "gid": gid,
                    "bhost": f"bridge{i}.test",
                    "bip": f"10.1.{i % 200}.1",
                    "bpool": bpool,
                },
            )

        # id exit при вставке парами: 1,3,5,... = 2*i-1 для i-й пары по порядку вставки
        def exit_id_for_pair_index(i: int) -> int:
            return 2 * i - 1

        for i in range(1, PAIRS + 1):
            sid = exit_id_for_pair_index(i)
            if i <= 8:
                n = LIGHT
            else:
                n = HEAVY
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
    print(f"  Пар: {PAIRS}, тяжёлый онлайн на exit: {HEAVY}, лёгкий: {LIGHT}")
    print("  Лёгкие nl:     пары i=1..4   (exit id 1,3,5,7)")
    print("  Лёгкие bypass: пары i=5..8   (exit id 9,11,13,15)")
    print("  Тяжёлые nl:    i=9..29;  bypass: i=30..50")
    return 0


if __name__ == "__main__":
    sys.exit(main())
