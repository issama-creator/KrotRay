from __future__ import annotations

import logging
import os

from services.minimal_lb import get_redis, load_server_ids, tcp_healthcheck

logger = logging.getLogger(__name__)


HEALTH_PORT = int(os.getenv("HEALTH_CHECK_PORT", "443"))
HEALTH_TIMEOUT_SEC = float(os.getenv("HEALTH_CHECK_TIMEOUT_SEC", "1.5"))


def run_server_health_check() -> None:
    client = get_redis()
    server_ids = load_server_ids(client)
    alive = 0
    dead = 0
    for server_id in server_ids:
        key = f"server:{server_id}"
        host = (client.hget(key, "host") or "").strip() or str(server_id)
        ok = tcp_healthcheck(host=host, port=HEALTH_PORT, timeout_sec=HEALTH_TIMEOUT_SEC)
        status = "alive" if ok else "dead"
        client.hset(key, mapping={"status": status})
        if ok:
            alive += 1
        else:
            dead += 1
    logger.info("health_check scanned=%s alive=%s dead=%s", len(server_ids), alive, dead)
