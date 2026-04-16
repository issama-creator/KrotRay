#!/usr/bin/env python3
"""
Ramp-симуляция Edge LB:
  - (опционально) создаёт N пар exit+bridge в edge_servers (через DATABASE_URL)
  - в течение D секунд постепенно "подключает" пользователей: POST /config
  - после config каждый пользователь периодически шлёт POST /ping до конца симуляции
  - в конце печатает распределение выбора exit и (опционально) сверку с БД.
Примеры:
  # Засеять 300 пар и прогнать 60 секунд (локальный API)
  set DATABASE_URL=postgresql://...   (PowerShell)
  python scripts/simulate_edge_lb_ramp.py --base-url http://127.0.0.1:8000 --seed 300 --duration 60 --users 800

  # Только симуляция к прод-API (без сидов)
  python scripts/simulate_edge_lb_ramp.py --base-url https://krotray.ru --duration 60 --users 2000
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
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class SimResult:
    exit_id: str | None
    err: str | None


def _seed_pairs_to_db(*, database_url: str, n_pairs: int, truncate: bool) -> None:
    from sqlalchemy import create_engine, text

    eng = create_engine(database_url)
    with eng.begin() as conn:
        if truncate:
            conn.execute(text("TRUNCATE TABLE edge_servers RESTART IDENTITY CASCADE"))
        for i in range(1, n_pairs + 1):
            gid = f"g{i:03d}"
            conn.execute(
                text(
                    """
                    INSERT INTO edge_servers (name, type, group_id, host, real_ip, is_active)
                    VALUES (:name, 'exit', :gid, :host, :ip, true)
                    """
                ),
                {"name": f"exit-{i}", "gid": gid, "host": f"exit{i}.test", "ip": f"10.0.{i % 250}.1"},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO edge_servers (name, type, group_id, host, real_ip, is_active)
                    VALUES (:name, 'bridge', :gid, :host, :ip, true)
                    """
                ),
                {"name": f"bridge-{i}", "gid": gid, "host": f"bridge{i}.test", "ip": f"10.1.{i % 250}.1"},
            )


def _query_db_counts(*, database_url: str, online_sec: int) -> list[tuple[int, int]]:
    from sqlalchemy import create_engine, text

    eng = create_engine(database_url)
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT d.server_id, COUNT(*)::int AS c
                FROM edge_devices d
                WHERE d.last_seen > NOW() - (:online_sec * INTERVAL '1 second')
                GROUP BY d.server_id
                ORDER BY c DESC, d.server_id ASC
                """
            ),
            {"online_sec": online_sec},
        ).all()
    return [(int(r[0]), int(r[1])) for r in rows]


def _simulate_one_user(
    *,
    base_url: str,
    stop_at: float,
    ping_interval: float,
    timeout: float,
) -> SimResult:
    did = f"sim-{uuid.uuid4()}"
    base = base_url.rstrip("/")
    s = requests.Session()
    try:
        r = s.post(f"{base}/config", json={"device_id": did, "key": None}, timeout=timeout)
        if r.status_code != 200:
            return SimResult(None, f"config_http_{r.status_code}")
        data = r.json()
        key = (data.get("key") or "").strip()
        if not key:
            return SimResult(None, "config_missing_key")
        servers: list[dict[str, Any]] = data.get("servers") or []
        if not servers:
            return SimResult(None, "config_empty_servers")
        chosen = random.choice(servers)
        eid = chosen.get("id")
        if eid is None:
            return SimResult(None, "config_no_server_id")

        # ping loop until stop_at
        while time.time() < stop_at:
            pr = s.post(
                f"{base}/ping",
                json={"device_id": did, "server_id": int(eid), "key": key},
                timeout=timeout,
            )
            if pr.status_code != 200:
                return SimResult(None, f"ping_http_{pr.status_code}")
            # jitter to avoid thundering herd
            sleep_for = max(0.05, ping_interval + random.uniform(-0.2 * ping_interval, 0.2 * ping_interval))
            time.sleep(sleep_for)

        return SimResult(str(eid), None)
    except Exception as e:
        return SimResult(None, f"exc:{e!s}"[:120])


def main() -> int:
    p = argparse.ArgumentParser(description="Edge LB ramp simulation (config+ping)")
    p.add_argument("--base-url", default=os.environ.get("EDGE_LB_BASE_URL", "http://127.0.0.1:8000"))
    p.add_argument("--users", type=int, default=1200, help="сколько виртуальных клиентов создать за ramp-секунд")
    p.add_argument("--duration", type=float, default=60.0, help="общая длительность симуляции, секунд")
    p.add_argument("--ramp", type=float, default=60.0, help="за сколько секунд создать всех пользователей")
    p.add_argument("--workers", type=int, default=120, help="параллельных потоков")
    p.add_argument("--ping-interval", type=float, default=20.0, help="интервал ping одного клиента, секунд")
    p.add_argument("--timeout", type=float, default=20.0, help="timeout HTTP запросов, секунд")
    p.add_argument("--seed", type=int, default=0, metavar="N", help="если >0: засидить N пар exit+bridge в БД")
    p.add_argument(
        "--truncate-seed",
        action="store_true",
        help="с --seed: перед сидом очистить edge_servers/edge_devices (TRUNCATE ... CASCADE)",
    )
    p.add_argument("--query-db", action="store_true", help="после симуляции вывести распределение из БД")
    p.add_argument("--online-sec", type=int, default=86400, help="окно online для сверки БД (сек)")
    args = p.parse_args()

    if args.seed:
        dbu = os.environ.get("DATABASE_URL")
        if not dbu:
            print("Для --seed нужен DATABASE_URL в окружении.", file=sys.stderr)
            return 2
        print(f"Seed: {args.seed} пар exit+bridge (truncate={args.truncate_seed})", flush=True)
        _seed_pairs_to_db(database_url=dbu, n_pairs=args.seed, truncate=args.truncate_seed)

    total_users = int(args.users)
    stop_at = time.time() + float(args.duration)
    ramp_sec = max(0.001, float(args.ramp))
    base = args.base_url.rstrip("/")

    print(
        f"Ramp: base={base!r} users={total_users} duration={args.duration:.1f}s ramp={args.ramp:.1f}s "
        f"workers={args.workers} ping_interval={args.ping_interval:.1f}s",
        flush=True,
    )

    counter: Counter[str] = Counter()
    err_counter: Counter[str] = Counter()
    t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = []
        for i in range(total_users):
            # равномерная подача пользователей в течение ramp_sec
            target = t0 + (i / max(1, total_users - 1)) * ramp_sec
            while time.perf_counter() < target:
                time.sleep(0.002)
            futures.append(
                ex.submit(
                    _simulate_one_user,
                    base_url=base,
                    stop_at=stop_at,
                    ping_interval=float(args.ping_interval),
                    timeout=float(args.timeout),
                )
            )

        for fut in as_completed(futures):
            res = fut.result()
            if res.exit_id is not None:
                counter[res.exit_id] += 1
            else:
                err_counter[res.err or "unknown"] += 1

    dt = time.perf_counter() - t0
    ok = sum(counter.values())
    bad = sum(err_counter.values())
    print(f"\nГотово за {dt:.1f}s. OK={ok} ERR={bad}", flush=True)
    if err_counter:
        print("Топ ошибок:", err_counter.most_common(10))

    if counter:
        vals = list(counter.values())
        mx, mn = max(vals), min(vals)
        ratio = mx / mn if mn else float("inf")
        stdev = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        print(f"\nРаспределение по exit (по итоговому выбранному server_id):")
        for sid, n in counter.most_common(20):
            print(f"  server {sid} -> {n}")
        print(f"\nМетрики равномерности: servers={len(vals)} max/min={ratio:.2f} stdev={stdev:.2f}")

    if args.query_db:
        dbu = os.environ.get("DATABASE_URL")
        if not dbu:
            print("\n--query-db: нужен DATABASE_URL", file=sys.stderr)
            return 3
        print(f"\n--- Из БД (edge_devices, last_seen за {args.online_sec} сек) ---")
        for sid, c in _query_db_counts(database_url=dbu, online_sec=int(args.online_sec))[:30]:
            print(f"  server {sid} -> {c}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

