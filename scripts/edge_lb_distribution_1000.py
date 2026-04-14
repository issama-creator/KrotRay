#!/usr/bin/env python3
"""
Прогон 1000 виртуальных пользователей против edge LB (POST /config → пара → POST /ping).

Печатает распределение по exit (как в simulate_edge_lb_load.py). Если задан DATABASE_URL,
в конце дополнительно выводит агрегат из PostgreSQL (реальные счётчики edge_devices за 90 с).

Примеры:
  python scripts/edge_lb_distribution_1000.py
  python scripts/edge_lb_distribution_1000.py https://krotray.ru

Переменные окружения:
  EDGE_LB_BASE_URL — базовый URL API, если не передан аргументом (по умолчанию https://krotray.ru)
  DATABASE_URL      — опционально, чтобы включить сводку из БД
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "scripts" / "simulate_edge_lb_load.py"

USERS = 1000
WORKERS = 80


def main() -> int:
    base = (
        (sys.argv[1] if len(sys.argv) > 1 else None)
        or os.environ.get("EDGE_LB_BASE_URL")
        or "https://krotray.ru"
    )
    cmd = [
        sys.executable,
        str(SIM),
        "--base-url",
        base,
        "--users",
        str(USERS),
        "--workers",
        str(WORKERS),
        "--ping-rounds",
        "2",
        "--fast",
    ]
    if os.environ.get("DATABASE_URL"):
        cmd.append("--query-db")
    print(
        f"Запуск: {USERS} пользователей, workers={WORKERS}, base={base!r}, "
        f"query_db={'да' if '--query-db' in cmd else 'нет (задай DATABASE_URL)'}",
        flush=True,
    )
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
