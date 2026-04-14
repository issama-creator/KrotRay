#!/usr/bin/env python3
"""
Симуляция: виртуальные пользователи вызывают POST /config и POST /ping (exit).

Запуск (локально к API):
  pip install requests
  python scripts/simulate_edge_lb_load.py --base-url http://127.0.0.1:8000 --users 1000

Перед этим в БД должны быть строки в edge_servers (exit+bridge с одним group_id).

Сид в консоль (только печать SQL, без файла):
  python scripts/simulate_edge_lb_load.py --emit-seed-sql 100

Сид сразу в PostgreSQL (в консоль печатается каждый INSERT, затем выполняется):
  export DATABASE_URL=postgresql://...
  python scripts/simulate_edge_lb_load.py --apply-seed 100

Пайп в psql (всё в консоль / на вход psql):
  python scripts/simulate_edge_lb_load.py --emit-seed-sql 100 | psql "$DATABASE_URL"

Статистика «как в проде» по БД (если задан DATABASE_URL):
  export DATABASE_URL=postgresql://...
  python scripts/simulate_edge_lb_load.py --base-url http://127.0.0.1:8000 --users 200 --query-db
"""
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

# Задержки: имитация сети между запросами одного пользователя
DELAY_AFTER_CONFIG = (0.05, 0.35)
DELAY_AFTER_PING = (0.05, 0.25)
# Между двумя пингами (как «живой» клиент раз в ~10 с)
DELAY_BETWEEN_PING_ROUNDS_DEFAULT = 10.0
DELAY_BETWEEN_PING_ROUNDS_FAST = 0.25


def iter_seed_inserts(n_pairs: int):
    """Yields INSERT без завершающей «;» — удобно и для text(), и для печати с «;»."""
    for i in range(1, n_pairs + 1):
        gid = f"g{i:03d}"
        yield (
            "INSERT INTO edge_servers (name, type, group_id, host, real_ip, is_active) "
            f"VALUES ('exit-{i}', 'exit', '{gid}', 'exit{i}.test', '10.0.0.{i % 250}', true)"
        )
        yield (
            "INSERT INTO edge_servers (name, type, group_id, host, real_ip, is_active) "
            f"VALUES ('bridge-{i}', 'bridge', '{gid}', 'bridge{i}.test', '10.1.0.{i % 250}', true)"
        )


def emit_seed_sql_to_console(n_pairs: int) -> None:
    """Только вывод в консоль (stdout)."""
    for stmt in iter_seed_inserts(n_pairs):
        print(f"{stmt};", flush=True)


def apply_seed_to_db(n_pairs: int, database_url: str) -> None:
    """Печать каждого INSERT в консоль и выполнение в PostgreSQL."""
    from sqlalchemy import create_engine, text

    stmts = list(iter_seed_inserts(n_pairs))
    print(f"-- Всего {len(stmts)} INSERT в edge_servers (пары exit+bridge)\n", flush=True)
    eng = create_engine(database_url)
    with eng.begin() as conn:
        for stmt in stmts:
            print(f"{stmt};", flush=True)
            conn.execute(text(stmt))
    print(f"\n-- Готово: применено {len(stmts)} строк.", flush=True)


def simulate_one_user(
    base_url: str,
    session: requests.Session,
    ping_rounds: int,
    sleep_between_pings: float,
) -> tuple[str | None, str | None]:
    """
    Один виртуальный пользователь: /config -> выбор exit -> /ping (1..ping_rounds раз).
    Возвращает (device_id, exit_server_id_str) при успехе, иначе (None, error_tag).
    """
    did = str(uuid.uuid4())
    base = base_url.rstrip("/")
    try:
        time.sleep(random.uniform(*DELAY_AFTER_CONFIG))
        r = session.post(f"{base}/config", json={}, timeout=60)
        if r.status_code != 200:
            return None, f"config_http_{r.status_code}"
        data = r.json()
        servers: list = data.get("servers") or []
        if not servers:
            return None, "config_empty_servers"

        # Как будто пользователь выбирает одну из выданных пар (случайно — меньше склейки на первый exit)
        pair = random.choice(servers)
        exit_block = pair.get("exit") or {}
        eid = exit_block.get("id")
        if eid is None:
            return None, "config_no_exit_id"

        time.sleep(random.uniform(*DELAY_AFTER_PING))
        for round_i in range(ping_rounds):
            pr = session.post(
                f"{base}/ping",
                json={"device_id": did, "server_id": int(eid)},
                timeout=30,
            )
            if pr.status_code != 200:
                return None, f"ping_http_{pr.status_code}_r{round_i}"
            if round_i + 1 < ping_rounds:
                time.sleep(sleep_between_pings)

        return str(eid), None
    except Exception as e:
        return None, f"exc:{e!s}"[:80]


def query_db_counts(database_url: str) -> list[tuple[int, int]]:
    """Сколько «онлайн» устройств на каждом exit (как в edge_lb_api: 90 сек)."""
    from sqlalchemy import create_engine, text

    eng = create_engine(database_url)
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT d.server_id, COUNT(*)::int AS c
                FROM edge_devices d
                WHERE d.last_seen > NOW() - (90 * INTERVAL '1 second')
                GROUP BY d.server_id
                ORDER BY c DESC, d.server_id
                """
            )
        ).all()
    return [(int(r[0]), int(r[1])) for r in rows]


def main() -> int:
    p = argparse.ArgumentParser(description="Симуляция нагрузки POST /config + POST /ping")
    p.add_argument("--base-url", default=os.environ.get("EDGE_LB_BASE_URL", "http://127.0.0.1:8000"))
    p.add_argument("--users", type=int, default=1000)
    p.add_argument("--workers", type=int, default=40, help="параллельных «пользователей»")
    p.add_argument("--ping-rounds", type=int, default=2, help="сколько раз подряд /ping на одного exit")
    p.add_argument(
        "--fast",
        action="store_true",
        help="короткая пауза между пингами вместо ~10 с (для быстрого прогона)",
    )
    p.add_argument("--query-db", action="store_true", help="после симуляции вывести агрегат из PostgreSQL")
    seed = p.add_mutually_exclusive_group()
    seed.add_argument(
        "--emit-seed-sql",
        type=int,
        metavar="N",
        help="напечатать в консоль N пар INSERT (exit+bridge), без записи в БД",
    )
    seed.add_argument(
        "--apply-seed",
        type=int,
        metavar="N",
        help="напечатать в консоль и выполнить N пар INSERT; нужен DATABASE_URL",
    )
    args = p.parse_args()

    if args.apply_seed is not None:
        dbu = os.environ.get("DATABASE_URL")
        if not dbu:
            print("Для --apply-seed задайте переменную окружения DATABASE_URL.", file=sys.stderr, flush=True)
            return 1
        apply_seed_to_db(args.apply_seed, dbu)
        return 0

    if args.emit_seed_sql is not None:
        emit_seed_sql_to_console(args.emit_seed_sql)
        return 0

    sleep_between = DELAY_BETWEEN_PING_ROUNDS_FAST if args.fast else DELAY_BETWEEN_PING_ROUNDS_DEFAULT

    print(
        f"Симуляция: base={args.base_url!r} users={args.users} workers={args.workers} "
        f"ping_rounds={args.ping_rounds} sleep_between_pings={sleep_between}s (fast={args.fast})",
        flush=True,
    )

    # Один Session на поток не thread-safe в requests — создаём session внутри worker через local pattern:
    # проще: без session, requests.post внутри simulate_one_user с новым соединением каждый раз (проще для демо)

    def task(_: int) -> tuple[str | None, str | None]:
        s = requests.Session()
        return simulate_one_user(args.base_url, s, args.ping_rounds, sleep_between)

    counter: Counter[str] = Counter()
    err_counter: Counter[str] = Counter()
    t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(task, i) for i in range(args.users)]
        for fut in as_completed(futures):
            eid, err = fut.result()
            if eid is not None:
                counter[eid] += 1
            else:
                err_counter[err or "unknown"] += 1

    dt = time.perf_counter() - t0
    print(f"\nГотово за {dt:.1f}s. Успешных пользователей: {sum(counter.values())}, ошибок: {sum(err_counter.values())}")
    if err_counter:
        print("Топ ошибок:", err_counter.most_common(8))

    if not counter:
        print("\nНет успешных ответов — проверь edge_servers и что API поднят.")
        return 1

    print("\nТоп exit server_id по числу пользователей (по успешным симуляциям, кто дошёл до пинга):")
    for sid, n in counter.most_common():
        print(f"  server {sid} → {n} users")

    vals = list(counter.values())
    if len(vals) > 1:
        mx, mn = max(vals), min(vals)
        ratio = mx / mn if mn else float("inf")
        stdev = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        print(f"\nРавномерность (чем ближе max/min к 1.0 и меньше stdev — тем ровнее):")
        print(f"  max/min = {ratio:.2f}   stdev = {stdev:.2f}   серверов с нагрузкой = {len(vals)}")

    if args.query_db:
        dbu = os.environ.get("DATABASE_URL")
        if not dbu:
            print("\n--query-db: задайте DATABASE_URL в окружении.")
            return 1
        print("\n--- Из БД (edge_devices, last_seen за 90 с) ---")
        try:
            for sid, c in query_db_counts(dbu):
                print(f"  server {sid} → {c} users")
        except Exception as e:
            print("Ошибка запроса БД:", e)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
