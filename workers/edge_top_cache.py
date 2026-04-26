"""Build and cache top edge candidates in Redis for fast /config."""
from __future__ import annotations

import logging

from db.session import SessionLocal
from services.edge_top_cache import build_top_candidates_payload, save_top_candidates

logger = logging.getLogger(__name__)


def run_edge_top_cache_refresh() -> None:
    db = SessionLocal()
    try:
        payload = build_top_candidates_payload(db)
        cached = save_top_candidates(payload)
        logger.info(
            "edge_top_cache: refreshed direct=%s bypass=%s cached=%s",
            len(payload.get("direct", [])),
            len(payload.get("bypass", [])),
            cached,
        )
    except Exception:
        logger.exception("edge_top_cache: refresh failed")
    finally:
        db.close()

