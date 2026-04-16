#!/usr/bin/env python3
"""
1-минутная симуляция для УЖЕ существующих edge_servers:
  - постепенно создаёт виртуальных пользователей (POST /config)
  - каждый пользователь выбирает один из выданных exit и шлёт POST /ping до конца минуты
  - печатает распределение по exit (какие server_id чаще выбирались)

Примеры:
  py -3 scripts/simulate_edge_lb_existing_1min.py --base-url https://krotray.ru
  py -3 scripts/simulate_edge_lb_existing_1min.py --base-url http://127.0.0.1:8000 --users 500 --workers 60
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class Result:
    exit_id: str | None
    err: str | None


def simulate_user(*, base_url: str, stop_at: float, ping_interval: float, timeout: float) -> Result:
    did = f"sim-{uuid.uuid4()}"
    base = base_url.rstrip("/")
    s = requests.Session()
    try:
        r = s.post(f"{base}/config", json={"device_id": did, "key": None}, timeout=timeout)
        if r.status_code != 200:
            return Result(None, f"config_http_{r.status_code}")
        data = r.json()
        key = (data.get("key") or "").strip()
        if not key:
            return Result(None, "config_missing_key")
        servers = data.get("servers") or []
        if not servers:
            return Result(None, "config_empty_servers")

        chosen = random.choice(list(servers))
        eid = chosen.get("id")
        if eid is None:
            return Result(None, "config_no_server_id")

        while time.time() < stop_at:
            pr = s.post(
                f"{base}/ping",
                json={"device_id": did, "server_id": int(eid), "key": key},
                timeout=timeout,
            )
            if pr.status_code != 200:
                return Result(None, f"ping_http_{pr.status_code}")
            # небольшой jitter
            time.sleep(max(0.05, ping_interval + random.uniform(-0.2 * ping_interval, 0.2 * ping_interval)))

        return Result(str(eid), None)
    except Exception as e:
        return Result(None, f"exc:{e!s}"[:120])


def main() -> int:
    p = argparse.ArgumentParser(description="Edge LB simulation on existing servers (1 minute)")
    p.add_argument("--base-url", default="https://krotray.ru")
    p.add_argument("--users", type=int, default=1200, help="сколько клиентов создать за минуту")
    p.add_argument("--duration", type=float, default=60.0, help="длительность симуляции, секунд")
    p.add_argument("--ramp", type=float, default=60.0, help="за сколько секунд создать всех пользователей")
    p.add_argument("--workers", type=int, default=120, help="параллельных потоков")
    p.add_argument("--ping-interval", type=float, default=20.0, help="интервал ping одного клиента, секунд")
    p.add_argument("--timeout", type=float, default=20.0, help="timeout HTTP, секунд")
    args = p.parse_args()

    total_users = int(args.users)
    stop_at = time.time() + float(args.duration)
    ramp_sec = max(0.001, float(args.ramp))

    print(
        f"Sim: base={args.base_url!r} users={total_users} duration={args.duration:.1f}s ramp={args.ramp:.1f}s "
        f"workers={args.workers} ping_interval={args.ping_interval:.1f}s",
        flush=True,
    )

    counter: Counter[str] = Counter()
    err_counter: Counter[str] = Counter()
    t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = []
        for i in range(total_users):
            target = t0 + (i / max(1, total_users - 1)) * ramp_sec
            while time.perf_counter() < target:
                time.sleep(0.002)
            futures.append(
                ex.submit(
                    simulate_user,
                    base_url=args.base_url,
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

    ok = sum(counter.values())
    bad = sum(err_counter.values())
    print(f"\nOK={ok} ERR={bad}", flush=True)
    if err_counter:
        print("Топ ошибок:", err_counter.most_common(10))

    if not counter:
        print("Нет успешных подключений. Проверь, что /config и /ping доступны.", file=sys.stderr)
        return 1

    vals = list(counter.values())
    mx, mn = max(vals), min(vals)
    ratio = mx / mn if mn else float("inf")
    stdev = statistics.pstdev(vals) if len(vals) > 1 else 0.0

    print("\nТоп exit server_id по числу пользователей (первые 30):")
    for sid, n in counter.most_common(30):
        print(f"  server {sid} -> {n}")
    print(f"\nРовность: servers={len(vals)} max/min={ratio:.2f} stdev={stdev:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

