"""Periodic cleanup for expired/stopped edge sessions."""
from __future__ import annotations

import logging

from sqlalchemy import text

from db.session import SessionLocal

logger = logging.getLogger(__name__)


def run_edge_sessions_cleanup() -> None:
    db = SessionLocal()
    try:
        result = db.execute(
            text(
                """
                DELETE FROM edge_sessions
                WHERE expires_at < NOW()
                   OR stopped_at IS NOT NULL
                """
            )
        )
        db.commit()
        logger.info("edge_sessions_cleanup: rows_deleted=%s", result.rowcount or 0)
    except Exception:
        logger.exception("edge_sessions_cleanup: failed")
        db.rollback()
    finally:
        db.close()

