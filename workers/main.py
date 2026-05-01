"""Single-purpose worker: TCP health checks for Redis server catalog."""
from __future__ import annotations

import logging
import os
import signal
import time

from workers.server_health import run_server_health_check

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_STOP = False

HEALTH_INTERVAL_SEC = int(os.getenv("HEALTH_CHECK_INTERVAL_SEC", "45"))


def _handle_stop(signum, _frame) -> None:  # type: ignore[no-untyped-def]
    global _STOP
    logger.info("workers_main: received signal=%s, stopping", signum)
    _STOP = True


def main() -> int:
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    sleep_sec = min(60, max(30, HEALTH_INTERVAL_SEC))
    logger.info("workers_main: health-check only interval=%ss", sleep_sec)

    try:
        while not _STOP:
            try:
                run_server_health_check()
            except Exception:
                logger.exception("workers_main: health-check cycle failed")
            for _ in range(sleep_sec):
                if _STOP:
                    break
                time.sleep(1)
    finally:
        logger.info("workers_main: stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
