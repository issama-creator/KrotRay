"""Periodic cleanup for stale VPN connection heartbeats."""
from __future__ import annotations

import logging

from sqlalchemy import text

from db.session import SessionLocal

logger = logging.getLogger(__name__)


def run_vpn_connections_cleanup() -> None:
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                """
                DELETE FROM connections
                WHERE last_seen < NOW() - INTERVAL '10 minutes'
                """
            )
        )
        db.commit()
        logger.info("vpn_connections_cleanup: rows_deleted=%s", result.rowcount or 0)
    except Exception:
        logger.exception("vpn_connections_cleanup: failed")
        db.rollback()
    finally:
        db.close()

