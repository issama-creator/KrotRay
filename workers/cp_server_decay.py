"""Плавное снижение current_users на cp_servers каждые 2 мин.

Эквивалент в PostgreSQL: UPDATE cp_servers SET current_users = GREATEST(current_users - 5, 0) WHERE active.
Здесь CASE — для совместимости с SQLite (у старых сборок нет GREATEST).
"""
from __future__ import annotations

import logging

from sqlalchemy import case, update

from db.models.cp_server import CpServer
from db.session import SessionLocal

logger = logging.getLogger(__name__)


def run_cp_server_load_decay() -> None:
    db = SessionLocal()
    try:
        stmt = (
            update(CpServer)
            .where(CpServer.active.is_(True))
            .values(
                current_users=case(
                    (CpServer.current_users > 5, CpServer.current_users - 5),
                    else_=0,
                ),
            )
        )
        result = db.execute(stmt)
        db.commit()
        logger.info("cp_server_decay: rows_updated=%s", result.rowcount)
    except Exception:
        logger.exception("cp_server_decay: failed")
        db.rollback()
    finally:
        db.close()
