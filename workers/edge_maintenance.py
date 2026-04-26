"""Unified edge maintenance worker: cleanup + cache + periodic health."""
from __future__ import annotations

import logging
import os
import time

from workers.edge_health import run_edge_health
from workers.edge_sessions_cleanup import run_edge_sessions_cleanup
from workers.edge_top_cache import run_edge_top_cache_refresh

logger = logging.getLogger(__name__)
EDGE_HEALTH_INTERVAL_SEC = int(os.getenv("EDGE_HEALTH_INTERVAL_SEC", "30"))
_last_health_run_monotonic = 0.0


def run_edge_maintenance() -> None:
    global _last_health_run_monotonic

    run_edge_sessions_cleanup()
    run_edge_top_cache_refresh()

    now_mono = time.monotonic()
    should_run_health = (
        _last_health_run_monotonic <= 0.0
        or (now_mono - _last_health_run_monotonic) >= max(1, EDGE_HEALTH_INTERVAL_SEC)
    )
    if should_run_health:
        run_edge_health()
        _last_health_run_monotonic = now_mono

    logger.info("edge_maintenance: cleanup+cache_refresh done health=%s", should_run_health)

