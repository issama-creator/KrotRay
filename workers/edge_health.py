"""Background health checker for edge_servers."""
from __future__ import annotations

import logging
import os
import socket
from datetime import datetime, timezone

from sqlalchemy import text

from db.session import SessionLocal

logger = logging.getLogger(__name__)

EDGE_HEALTH_TIMEOUT_SEC = float(os.getenv("EDGE_HEALTH_TIMEOUT_SEC", "1.5"))
EDGE_HEALTH_PORT = int(os.getenv("EDGE_HEALTH_PORT", "443"))
EDGE_FAIL_THRESHOLD = int(os.getenv("EDGE_FAIL_THRESHOLD", "3"))
EDGE_RECOVER_THRESHOLD = int(os.getenv("EDGE_RECOVER_THRESHOLD", "2"))


def _is_host_alive(host: str, port: int, timeout_sec: float) -> tuple[bool, str | None]:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True, None
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def run_edge_health() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT id, host, is_active, fail_count, success_count
                FROM edge_servers
                WHERE type = 'exit'
                ORDER BY id ASC
                """
            )
        ).mappings().all()
        if not rows:
            return

        now = datetime.now(timezone.utc)
        updates: list[dict] = []
        changed_active = 0
        failed_checks = 0

        for row in rows:
            sid = int(row["id"])
            host = str(row.get("host") or "").strip()
            is_active = bool(row.get("is_active"))
            fail_count = int(row.get("fail_count") or 0)
            success_count = int(row.get("success_count") or 0)

            ok, err = _is_host_alive(host, EDGE_HEALTH_PORT, EDGE_HEALTH_TIMEOUT_SEC)
            if ok:
                success_count += 1
                fail_count = 0
                next_active = is_active or (success_count >= EDGE_RECOVER_THRESHOLD)
                if next_active != is_active:
                    changed_active += 1
                updates.append(
                    {
                        "id": sid,
                        "is_active": next_active,
                        "fail_count": fail_count,
                        "success_count": success_count,
                        "last_check_at": now,
                        "last_ok_at": now,
                        "last_error": None,
                    }
                )
            else:
                failed_checks += 1
                fail_count += 1
                success_count = 0
                next_active = False if (is_active and fail_count >= EDGE_FAIL_THRESHOLD) else is_active
                if next_active != is_active:
                    changed_active += 1
                updates.append(
                    {
                        "id": sid,
                        "is_active": next_active,
                        "fail_count": fail_count,
                        "success_count": success_count,
                        "last_check_at": now,
                        "last_ok_at": None,
                        "last_error": (err or "health check failed")[:500],
                    }
                )

        db.execute(
            text(
                """
                UPDATE edge_servers
                SET
                    is_active = :is_active,
                    fail_count = :fail_count,
                    success_count = :success_count,
                    last_check_at = :last_check_at,
                    last_ok_at = COALESCE(:last_ok_at, last_ok_at),
                    last_error = :last_error
                WHERE id = :id
                """
            ),
            updates,
        )
        db.commit()
        logger.info(
            "edge_health: checked=%s failed=%s active_toggled=%s",
            len(updates),
            failed_checks,
            changed_active,
        )
    except Exception:
        logger.exception("edge_health: failed")
        db.rollback()
    finally:
        db.close()

