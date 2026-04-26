#!/usr/bin/env python3
"""
Steady-state simulation:
- bootstrap N clients via POST /config
- every interval (e.g. 60s) each client sends POST /ping
- prints per-round distribution by server_id

Example:
  python scripts/simulate_steady_heartbeats.py \
    --base-url https://krotray.ru \
    --users 300 \
    --duration-sec 600 \
    --interval-sec 60 \
    --workers 80
"""
from __future__ import annotations

import argparse
import random
import statistics
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

CONFIG_TIMEOUT = 12.0
PING_TIMEOUT = 12.0


@dataclass(frozen=True)
class ClientState:
    device_id: str
    key: str
    server_id: int


@dataclass(frozen=True)
class PingResult:
    ok: bool
    latency_ms: float
    server_id: int | None
    error: str | None


def _post_config(base_url: str, device_id: str) -> tuple[bool, ClientState | None, str | None]:
    s = requests.Session()
    try:
        r = s.post(
            f"{base_url.rstrip('/')}/config",
            json={"device_id": device_id, "key": None},
            timeout=CONFIG_TIMEOUT,
        )
        if r.status_code != 200:
            return False, None, f"config_http_{r.status_code}"
        payload = r.json()
        key = (payload.get("key") or "").strip()
        servers = payload.get("servers") or []
        if not key:
            return False, None, "config_missing_key"
        if not servers:
            return False, None, "config_empty_servers"

        # Берем случайный выданный сервер, чтобы в steady-тесте не было перекоса только в first server.
        picked = random.choice(servers)
        sid = picked.get("id")
        if sid is None:
            return False, None, "config_server_id_missing"
        state = ClientState(device_id=device_id, key=key, server_id=int(sid))
        return True, state, None
    except Exception as e:  # noqa: BLE001
        return False, None, f"config_exc:{e!s}"[:180]


def _post_ping(base_url: str, state: ClientState) -> PingResult:
    s = requests.Session()
    started = time.perf_counter()
    try:
        r = s.post(
            f"{base_url.rstrip('/')}/ping",
            json={
                "device_id": state.device_id,
                "key": state.key,
                "server_id": state.server_id,
            },
            timeout=PING_TIMEOUT,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if r.status_code != 200:
            return PingResult(False, latency_ms, state.server_id, f"ping_http_{r.status_code}")
        return PingResult(True, latency_ms, state.server_id, None)
    except Exception as e:  # noqa: BLE001
        latency_ms = (time.perf_counter() - started) * 1000.0
        return PingResult(False, latency_ms, state.server_id, f"ping_exc:{e!s}"[:180])


def _bootstrap_clients(base_url: str, users: int, workers: int) -> list[ClientState]:
    states: list[ClientState] = []
    errors: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_post_config, base_url, f"steady-{i}-{uuid.uuid4()}")
            for i in range(users)
        ]
        for fut in as_completed(futures):
            ok, state, err = fut.result()
            if ok and state is not None:
                states.append(state)
            elif err:
                errors[err] += 1

    print(f"bootstrap: requested={users} ready={len(states)} failed={users - len(states)}")
    if errors:
        print("bootstrap_errors:", ", ".join(f"{k}={v}" for k, v in errors.most_common(8)))
    return states


def _ping_round(base_url: str, states: list[ClientState], workers: int, round_no: int) -> None:
    results: list[PingResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_post_ping, base_url, st) for st in states]
        for fut in as_completed(futures):
            results.append(fut.result())

    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    lats = [r.latency_ms for r in results]
    by_server: Counter[int] = Counter()
    for r in ok:
        if r.server_id is not None:
            by_server[int(r.server_id)] += 1

    print(f"\n=== ROUND {round_no} ===")
    print(f"ping_total={len(results)} ok={len(ok)} failed={len(failed)}")
    if lats:
        p95 = statistics.quantiles(lats, n=100)[94] if len(lats) >= 20 else max(lats)
        print(
            "latency_ms: avg={:.1f} p95={:.1f} max={:.1f}".format(
                statistics.mean(lats),
                p95,
                max(lats),
            )
        )
    if by_server:
        print("top_server_distribution:", ", ".join(f"{sid}:{cnt}" for sid, cnt in by_server.most_common(15)))
        vals = list(by_server.values())
        avg = statistics.mean(vals)
        mx = max(vals)
        print(f"distribution_skew=max/avg={mx / avg:.2f}")
    if failed:
        errc = Counter(r.error or "unknown" for r in failed)
        print("errors:", ", ".join(f"{k}={v}" for k, v in errc.most_common(10)))


def main() -> int:
    p = argparse.ArgumentParser(description="Steady heartbeat simulation")
    p.add_argument("--base-url", required=True, help="API base URL, e.g. https://krotray.ru")
    p.add_argument("--users", type=int, default=300, help="Number of clients to keep alive")
    p.add_argument("--duration-sec", type=int, default=600, help="Total test duration in seconds")
    p.add_argument("--interval-sec", type=int, default=60, help="Ping interval per client in seconds")
    p.add_argument("--workers", type=int, default=80, help="Thread pool size for parallel requests")
    args = p.parse_args()

    if args.users <= 0 or args.duration_sec <= 0 or args.interval_sec <= 0 or args.workers <= 0:
        raise SystemExit("All numeric args must be > 0")

    print(
        "steady test: base={} users={} duration={}s interval={}s workers={}".format(
            args.base_url,
            args.users,
            args.duration_sec,
            args.interval_sec,
            args.workers,
        )
    )

    states = _bootstrap_clients(args.base_url, args.users, args.workers)
    if not states:
        print("no clients ready; stop")
        return 1

    rounds = max(1, args.duration_sec // args.interval_sec)
    for i in range(1, rounds + 1):
        _ping_round(args.base_url, states, args.workers, i)
        if i < rounds:
            time.sleep(args.interval_sec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

