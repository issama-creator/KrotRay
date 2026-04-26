"""Dedicated worker process runner (without FastAPI/bot)."""
from __future__ import annotations

import logging
import signal
import time

from apscheduler.schedulers.background import BackgroundScheduler

from api.expired_job import run_expired_subscriptions
from workers.cp_health import run_cp_health
from workers.cp_server_decay import run_cp_server_load_decay
from workers.edge_maintenance import run_edge_maintenance
from workers.vpn_connections_cleanup import run_vpn_connections_cleanup
from workers.vpn_server_balancer import run_vpn_server_balancer

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_STOP = False


def _handle_stop(signum, _frame) -> None:  # type: ignore[no-untyped-def]
    global _STOP
    logger.info("workers_main: received signal=%s, stopping", signum)
    _STOP = True


def main() -> int:
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    scheduler = BackgroundScheduler()
    scheduler.add_job(run_expired_subscriptions, "interval", minutes=5, id="expired_subs")
    scheduler.add_job(run_cp_health, "interval", seconds=120, id="cp_health")
    scheduler.add_job(run_cp_server_load_decay, "interval", minutes=2, id="cp_server_decay")
    scheduler.add_job(run_edge_maintenance, "interval", seconds=15, id="edge_maintenance")
    scheduler.add_job(run_vpn_server_balancer, "interval", seconds=5, id="vpn_server_balancer")
    scheduler.add_job(run_vpn_connections_cleanup, "interval", minutes=5, id="vpn_connections_cleanup")

    run_edge_maintenance()
    scheduler.start()
    logger.info("workers_main: scheduler started")

    try:
        while not _STOP:
            time.sleep(1)
    finally:
        scheduler.shutdown(wait=False)
        logger.info("workers_main: scheduler stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

