#!/usr/bin/env python3
"""
Steady-state simulation for session lifecycle:
- bootstrap clients via POST /config
- start sessions via POST /session/start
- every interval renew via POST /session/renew
- optional stop via POST /session/stop at the end

Example:
  python scripts/simulate_sessions_steady.py \
    --base-url https://krotray.ru \
    --users 500 \
    --duration-sec 120 \
    --interval-sec 60 \
    --workers 80 \
    --do-stop
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
SESSION_TIMEOUT = 12.0


@dataclass(frozen=True)
class ClientState:
    device_id: str
    key: str
    server_id: int
    session_id: str


@dataclass(frozen=True)
class OpResult:
    ok: bool
    latency_ms: float
    server_id: int | None
    error: str | None


def _pick_server_from_config(servers: list[dict], mode_policy: str) -> dict | None:
    if not servers:
        return None
    direct = [s for s in servers if str(s.get("mode") or "") == "direct"]
    bypass = [s for s in servers if str(s.get("mode") or "") == "bypass"]

    if mode_policy == "nl":
        return random.choice(direct) if direct else random.choice(servers)
    if mode_policy == "bypass":
        return random.choice(bypass) if bypass else random.choice(servers)
    if mode_policy == "balanced":
        if direct and bypass:
            pick_direct = bool(random.getrandbits(1))
            return random.choice(direct if pick_direct else bypass)
        return random.choice(servers)
    return random.choice(servers)


def _post_config(base_url: str, device_id: str, mode_policy: str) -> tuple[bool, ClientState | None, str | None]:
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

        picked = _pick_server_from_config(servers, mode_policy=mode_policy)
        if picked is None:
            return False, None, "config_pick_failed"
        sid = picked.get("id")
        if sid is None:
            return False, None, "config_server_id_missing"

        state = ClientState(
            device_id=device_id,
            key=key,
            server_id=int(sid),
            session_id=f"sess-{uuid.uuid4()}",
        )
        return True, state, None
    except Exception as e:  # noqa: BLE001
        return False, None, f"config_exc:{e!s}"[:180]


def _post_start(base_url: str, state: ClientState) -> OpResult:
    s = requests.Session()
    started = time.perf_counter()
    try:
        r = s.post(
            f"{base_url.rstrip('/')}/session/start",
            json={
                "device_id": state.device_id,
                "key": state.key,
                "server_id": state.server_id,
                "session_id": state.session_id,
            },
            timeout=SESSION_TIMEOUT,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if r.status_code != 200:
            return OpResult(False, latency_ms, state.server_id, f"start_http_{r.status_code}")
        payload = r.json()
        if not bool(payload.get("ok")):
            return OpResult(False, latency_ms, state.server_id, "start_not_ok")
        return OpResult(True, latency_ms, state.server_id, None)
    except Exception as e:  # noqa: BLE001
        latency_ms = (time.perf_counter() - started) * 1000.0
        return OpResult(False, latency_ms, state.server_id, f"start_exc:{e!s}"[:180])


def _post_renew(base_url: str, state: ClientState) -> OpResult:
    s = requests.Session()
    started = time.perf_counter()
    try:
        r = s.post(
            f"{base_url.rstrip('/')}/session/renew",
            json={
                "device_id": state.device_id,
                "key": state.key,
                "session_id": state.session_id,
            },
            timeout=SESSION_TIMEOUT,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if r.status_code != 200:
            return OpResult(False, latency_ms, state.server_id, f"renew_http_{r.status_code}")
        payload = r.json()
        if not bool(payload.get("ok")):
            return OpResult(False, latency_ms, state.server_id, "renew_not_ok")
        if not bool(payload.get("renewed")):
            return OpResult(False, latency_ms, state.server_id, "renewed_false")
        return OpResult(True, latency_ms, state.server_id, None)
    except Exception as e:  # noqa: BLE001
        latency_ms = (time.perf_counter() - started) * 1000.0
        return OpResult(False, latency_ms, state.server_id, f"renew_exc:{e!s}"[:180])


def _post_stop(base_url: str, state: ClientState) -> OpResult:
    s = requests.Session()
    started = time.perf_counter()
    try:
        r = s.post(
            f"{base_url.rstrip('/')}/session/stop",
            json={
                "device_id": state.device_id,
                "key": state.key,
                "session_id": state.session_id,
            },
            timeout=SESSION_TIMEOUT,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if r.status_code != 200:
            return OpResult(False, latency_ms, state.server_id, f"stop_http_{r.status_code}")
        payload = r.json()
        if not bool(payload.get("ok")):
            return OpResult(False, latency_ms, state.server_id, "stop_not_ok")
        return OpResult(True, latency_ms, state.server_id, None)
    except Exception as e:  # noqa: BLE001
        latency_ms = (time.perf_counter() - started) * 1000.0
        return OpResult(False, latency_ms, state.server_id, f"stop_exc:{e!s}"[:180])


def _print_round_stats(label: str, results: list[OpResult]) -> None:
    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    lats = [r.latency_ms for r in results]
    by_server: Counter[int] = Counter()
    for r in ok:
        if r.server_id is not None:
            by_server[int(r.server_id)] += 1

    print(f"\n=== {label} ===")
    print(f"total={len(results)} ok={len(ok)} failed={len(failed)}")
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


def _bootstrap_clients(base_url: str, users: int, workers: int, mode_policy: str) -> list[ClientState]:
    states: list[ClientState] = []
    errors: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_post_config, base_url, f"sess-{i}-{uuid.uuid4()}", mode_policy)
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


def _run_phase(
    base_url: str, states: list[ClientState], workers: int, phase: str
) -> list[tuple[ClientState, OpResult]]:
    fn = _post_start if phase == "start" else _post_renew if phase == "renew" else _post_stop
    results: list[tuple[ClientState, OpResult]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, base_url, st): st for st in states}
        for fut in as_completed(futures):
            st = futures[fut]
            results.append((st, fut.result()))
    return results


def main() -> int:
    p = argparse.ArgumentParser(description="Steady session lifecycle simulation")
    p.add_argument("--base-url", required=True, help="API base URL, e.g. https://krotray.ru")
    p.add_argument("--users", type=int, default=300, help="Number of clients")
    p.add_argument("--duration-sec", type=int, default=300, help="Total test duration in seconds")
    p.add_argument("--interval-sec", type=int, default=60, help="Renew interval in seconds")
    p.add_argument("--workers", type=int, default=80, help="Thread pool size")
    p.add_argument(
        "--mode-policy",
        choices=["random", "balanced", "nl", "bypass"],
        default="balanced",
        help="How to pick server from /config response",
    )
    p.add_argument("--do-stop", action="store_true", help="Send /session/stop for all clients at the end")
    args = p.parse_args()

    if args.users <= 0 or args.duration_sec <= 0 or args.interval_sec <= 0 or args.workers <= 0:
        raise SystemExit("All numeric args must be > 0")

    print(
        "session steady test: base={} users={} duration={}s renew_interval={}s workers={} do_stop={}".format(
            args.base_url,
            args.users,
            args.duration_sec,
            args.interval_sec,
            args.workers,
            args.do_stop,
        )
    )

    states = _bootstrap_clients(args.base_url, args.users, args.workers, args.mode_policy)
    if not states:
        print("no clients ready; stop")
        return 1

    start_pairs = _run_phase(args.base_url, states, args.workers, phase="start")
    _print_round_stats("START", [res for _, res in start_pairs])
    live_states = [st for st, res in start_pairs if res.ok]
    if not live_states:
        print("no started sessions; stop")
        return 1

    rounds = max(1, args.duration_sec // args.interval_sec)
    for i in range(1, rounds + 1):
        renew_pairs = _run_phase(args.base_url, live_states, args.workers, phase="renew")
        _print_round_stats(f"RENEW ROUND {i}", [res for _, res in renew_pairs])
        live_states = [st for st, res in renew_pairs if res.ok]
        if not live_states:
            print("all sessions dropped during renew; stop")
            return 1
        if i < rounds:
            time.sleep(args.interval_sec)

    if args.do_stop:
        stop_pairs = _run_phase(args.base_url, live_states, args.workers, phase="stop")
        _print_round_stats("STOP", [res for _, res in stop_pairs])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

