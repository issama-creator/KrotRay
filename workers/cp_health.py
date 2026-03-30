"""Health + latency для cp_servers: TCP :443, 3 с; 3 провала подряд → active=false; last_check всегда обновляется."""
from __future__ import annotations

import logging
import socket
import time
from datetime import datetime, timezone

from sqlalchemy import select

from db.models.cp_server import CpServer
from db.session import SessionLocal

logger = logging.getLogger(__name__)

TCP_PORT = 443
TIMEOUT_SEC = 3.0
FAIL_THRESHOLD = 3

_fail_streak: dict[int, int] = {}


def _tcp_probe(host: str, port: int = TCP_PORT, timeout: float = TIMEOUT_SEC) -> tuple[bool, int | None]:
    start = time.perf_counter_ns()
    sock: socket.socket | None = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        latency_ms = int((time.perf_counter_ns() - start) / 1_000_000)
        return True, latency_ms
    except OSError:
        return False, None
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


class CpServerHealthWorker:
    """Проверка доступности узлов, замер latency, флаг active."""

    @staticmethod
    def run() -> None:
        db = SessionLocal()
        now = datetime.now(timezone.utc)
        try:
            rows = db.scalars(select(CpServer)).all()
            for srv in rows:
                ok, latency_ms = _tcp_probe(srv.ip, TCP_PORT, TIMEOUT_SEC)
                srv.last_check = now
                if ok:
                    _fail_streak[srv.id] = 0
                    if latency_ms is not None:
                        srv.latency = latency_ms
                    srv.active = True
                    logger.info(
                        "cp_health: server_id=%s status=up latency_ms=%s",
                        srv.id,
                        latency_ms,
                    )
                else:
                    _fail_streak[srv.id] = _fail_streak.get(srv.id, 0) + 1
                    if _fail_streak[srv.id] >= FAIL_THRESHOLD:
                        srv.active = False
                        logger.error(
                            "cp_health: server_id=%s status=down latency_ms=null streak=%s",
                            srv.id,
                            _fail_streak[srv.id],
                        )
                    else:
                        logger.warning(
                            "cp_health: server_id=%s status=fail latency_ms=null streak=%s",
                            srv.id,
                            _fail_streak[srv.id],
                        )
                db.add(srv)
            db.commit()
            logger.info("cp_health: checked %s servers", len(rows))
        except Exception:
            logger.exception("cp_health: failed")
            db.rollback()
        finally:
            db.close()


def run_cp_health() -> None:
    CpServerHealthWorker.run()
