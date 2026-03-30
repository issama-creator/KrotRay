"""Сброс current_users на cp_servers каждые 10 минут (MVP: счётчик «за окно» между сбросами)."""
from __future__ import annotations

import logging

from sqlalchemy import select

from db.models.cp_server import CpServer
from db.session import SessionLocal

logger = logging.getLogger(__name__)


class CpServerLoadResetWorker:
    """Фоновый сброс нагрузки: current_users → 0 с логированием старых значений."""

    @staticmethod
    def run() -> None:
        db = SessionLocal()
        try:
            rows = db.scalars(select(CpServer)).all()
            for srv in rows:
                old = srv.current_users
                srv.current_users = 0
                db.add(srv)
                logger.info(
                    "cp_server_reset: server_id=%s old_current_users=%s new_current_users=0",
                    srv.id,
                    old,
                )
            db.commit()
            logger.info("cp_server_reset: reset %s servers", len(rows))
        except Exception:
            logger.exception("cp_server_reset: failed")
            db.rollback()
        finally:
            db.close()


def run_cp_server_current_users_reset() -> None:
    CpServerLoadResetWorker.run()
