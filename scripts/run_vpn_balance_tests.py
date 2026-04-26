#!/usr/bin/env python3
"""
Load tests for VPN balancing pipeline (/config + /ping).

Scenarios:
  1) ramp      - smooth growth: 50 -> 100 -> 300 -> 500 users
  2) spike     - sudden burst, e.g. 1000 users in seconds
  3) failover  - baseline load + mark one server dead + verify redistribution

Examples:
  python scripts/run_vpn_balance_tests.py ramp --base-url https://krotray.ru
  python scripts/run_vpn_balance_tests.py spike --base-url https://krotray.ru --users 1000 --workers 200
  python scripts/run_vpn_balance_tests.py failover --base-url https://krotray.ru --database-url postgresql://...
"""
from __future__ import annotations

import argparse
import random
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import requests
from sqlalchemy import create_engine, text


CONFIG_TIMEOUT = 10.0
PING_TIMEOUT = 10.0


@dataclass(frozen=True)
class UserResult:
    ok: bool
    latency_ms: float
    picked_server_ids: tuple[int, ...]
    error: str | None


def _config_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/config"


def _ping_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/ping"


def _run_user(base_url: str, user_key: str, do_ping: bool, config_mode: str) -> UserResult:
    started = time.perf_counter()
    s = requests.Session()
    try:
        if config_mode == "edge":
            r = s.post(
                _config_url(base_url),
                json={"device_id": f"dev-{user_key}", "key": None},
                timeout=CONFIG_TIMEOUT,
            )
        else:
            r = s.get(_config_url(base_url), params={"key": user_key}, timeout=CONFIG_TIMEOUT)
        latency_ms = (time.perf_counter() - started) * 1000.0
        if r.status_code != 200:
            return UserResult(False, latency_ms, (), f"config_http_{r.status_code}")
        payload = r.json()
        servers = payload.get("servers") or []
        server_ids = tuple(int(x.get("id")) for x in servers if isinstance(x, dict) and x.get("id") is not None)
        if not server_ids:
            return UserResult(False, latency_ms, (), "config_empty_servers")

        if do_ping:
            pr = s.post(
                _ping_url(base_url),
                json={"device_id": f"dev-{user_key}", "key": str(payload.get("key") or user_key), "server_id": int(server_ids[0])},
                timeout=PING_TIMEOUT,
            )
            if pr.status_code != 200:
                return UserResult(False, latency_ms, server_ids, f"ping_http_{pr.status_code}")

        return UserResult(True, latency_ms, server_ids, None)
    except Exception as e:  # noqa: BLE001
        latency_ms = (time.perf_counter() - started) * 1000.0
        return UserResult(False, latency_ms, (), f"exc:{e!s}"[:200])


def _run_batch(
    base_url: str,
    users: int,
    workers: int,
    do_ping: bool,
    key_prefix: str,
    config_mode: str,
) -> list[UserResult]:
    results: list[UserResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                _run_user,
                base_url,
                f"{key_prefix}-{i}-{random.randint(1, 10_000_000)}",
                do_ping,
                config_mode,
            )
            for i in range(users)
        ]
        for f in as_completed(futures):
            results.append(f.result())
    return results


def _summarize(results: list[UserResult], title: str) -> dict[str, Any]:
    ok = [r for r in results if r.ok]
    errs = [r.error for r in results if not r.ok]
    lats = [r.latency_ms for r in results]
    p95 = statistics.quantiles(lats, n=100)[94] if len(lats) >= 20 else (max(lats) if lats else 0.0)
    server_counter: Counter[int] = Counter()
    for r in ok:
        for sid in r.picked_server_ids:
            server_counter[sid] += 1

    print(f"\n=== {title} ===")
    print(f"requests_total={len(results)} ok={len(ok)} failed={len(results) - len(ok)}")
    if lats:
        print(
            "latency_ms: avg={:.1f} p95={:.1f} max={:.1f}".format(
                statistics.mean(lats),
                p95,
                max(lats),
            )
        )
    if server_counter:
        top = server_counter.most_common(12)
        print("top_server_distribution:", ", ".join(f"{sid}:{cnt}" for sid, cnt in top))
        counts = list(server_counter.values())
        avg = statistics.mean(counts)
        mx = max(counts)
        print(f"distribution_skew=max/avg={mx / avg:.2f}")
    if errs:
        ec = Counter(errs)
        print("errors:", ", ".join(f"{k}={v}" for k, v in ec.most_common(8)))

    return {
        "total": len(results),
        "ok": len(ok),
        "failed": len(results) - len(ok),
        "p95_ms": p95 if lats else 0.0,
        "server_counter": server_counter,
    }


def _db_top_load(database_url: str, limit: int = 12) -> list[tuple[int, float, float, str]]:
    eng = create_engine(database_url)
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, load, score, status
                FROM servers
                ORDER BY load DESC, id ASC
                LIMIT :lim
                """
            ),
            {"lim": limit},
        ).all()
    return [(int(r[0]), float(r[1] or 0.0), float(r[2] or 0.0), str(r[3])) for r in rows]


def _db_mark_dead(database_url: str, server_id: int) -> None:
    eng = create_engine(database_url)
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE servers
                SET status = 'dead', updated_at = NOW()
                WHERE id = :sid
                """
            ),
            {"sid": server_id},
        )


def run_ramp(args: argparse.Namespace) -> int:
    print(f"Ramp test: base={args.base_url} workers={args.workers} do_ping={args.do_ping}")
    stages = [50, 100, 300, 500]
    for users in stages:
        print(f"\n--- stage users={users} ---")
        started = time.time()
        while time.time() - started < args.stage_seconds:
            batch = _run_batch(
                base_url=args.base_url,
                users=users,
                workers=args.workers,
                do_ping=args.do_ping,
                key_prefix=f"ramp-{users}",
                config_mode=args.config_mode,
            )
            _summarize(batch, title=f"RAMP users={users}")
            if args.pause_seconds > 0:
                time.sleep(args.pause_seconds)
    return 0


def run_spike(args: argparse.Namespace) -> int:
    print(
        "Spike test: base={} users={} workers={} do_ping={}".format(
            args.base_url,
            args.users,
            args.workers,
            args.do_ping,
        )
    )
    t0 = time.perf_counter()
    batch = _run_batch(
        base_url=args.base_url,
        users=args.users,
        workers=args.workers,
        do_ping=args.do_ping,
        key_prefix="spike",
        config_mode=args.config_mode,
    )
    elapsed = time.perf_counter() - t0
    summary = _summarize(batch, title="SPIKE")
    print(f"elapsed_s={elapsed:.2f}")
    if summary["failed"] == 0 and summary["p95_ms"] < args.latency_ok_ms:
        print("result=OK")
    else:
        print("result=CHECK_REQUIRED")
    return 0


def run_failover(args: argparse.Namespace) -> int:
    print(f"Failover test: base={args.base_url} users={args.users} workers={args.workers}")
    before = _run_batch(
        base_url=args.base_url,
        users=args.users,
        workers=args.workers,
        do_ping=args.do_ping,
        key_prefix="failover-before",
        config_mode=args.config_mode,
    )
    before_summary = _summarize(before, title="FAILOVER before")
    if not before_summary["server_counter"]:
        print("no servers in baseline; abort")
        return 1

    target_server_id = before_summary["server_counter"].most_common(1)[0][0]
    print(f"candidate_to_fail server_id={target_server_id}")

    if args.database_url:
        _db_mark_dead(args.database_url, target_server_id)
        print(f"server_marked_dead id={target_server_id}")
    else:
        print("database_url not provided; mark server dead manually and press Enter...")
        input()

    if args.wait_after_fail_s > 0:
        time.sleep(args.wait_after_fail_s)

    after = _run_batch(
        base_url=args.base_url,
        users=args.users,
        workers=args.workers,
        do_ping=args.do_ping,
        key_prefix="failover-after",
        config_mode=args.config_mode,
    )
    after_summary = _summarize(after, title="FAILOVER after")
    still_served = int(after_summary["server_counter"].get(target_server_id, 0))
    print(f"failed_server_occurrences_after={still_served}")
    if still_served == 0:
        print("result=OK")
    else:
        print("result=CHECK_REQUIRED")

    if args.database_url:
        print("\nTop loads from DB:")
        for sid, load, score, status in _db_top_load(args.database_url):
            print(f"id={sid} load={load:.4f} score={score:.4f} status={status}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="VPN balancer load tests")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("ramp", help="Smooth ramp test")
    pr.add_argument("--base-url", required=True)
    pr.add_argument("--workers", type=int, default=100)
    pr.add_argument("--stage-seconds", type=int, default=300, help="Duration per stage (5 min default)")
    pr.add_argument("--pause-seconds", type=int, default=5)
    pr.add_argument("--do-ping", action="store_true", help="Also call POST /ping per user")
    pr.add_argument("--config-mode", choices=["edge", "vpn"], default="edge")
    pr.set_defaults(func=run_ramp)

    ps = sub.add_parser("spike", help="Sudden burst test")
    ps.add_argument("--base-url", required=True)
    ps.add_argument("--users", type=int, default=1000)
    ps.add_argument("--workers", type=int, default=250)
    ps.add_argument("--do-ping", action="store_true", help="Also call POST /ping per user")
    ps.add_argument("--config-mode", choices=["edge", "vpn"], default="edge")
    ps.add_argument("--latency-ok-ms", type=float, default=200.0)
    ps.set_defaults(func=run_spike)

    pf = sub.add_parser("failover", help="Failover test")
    pf.add_argument("--base-url", required=True)
    pf.add_argument("--users", type=int, default=400)
    pf.add_argument("--workers", type=int, default=120)
    pf.add_argument("--do-ping", action="store_true", help="Also call POST /ping per user")
    pf.add_argument("--config-mode", choices=["edge", "vpn"], default="edge")
    pf.add_argument("--database-url", default="", help="Optional DB url to auto-mark server dead")
    pf.add_argument("--wait-after-fail-s", type=int, default=10, help="Wait for workers to react")
    pf.set_defaults(func=run_failover)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

