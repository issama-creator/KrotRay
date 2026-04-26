"""Worker: updates servers load/score/cooldown in batch every tick."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import text

from db.session import SessionLocal
from services.vpn_balancer import calculate_score, check_spike, get_active_users_map

logger = logging.getLogger(__name__)

MAX_CONNECTIONS = int(os.getenv("VPN_MAX_CONNECTIONS", "1000"))
SPIKE_THRESHOLD = int(os.getenv("VPN_SPIKE_THRESHOLD", "20"))
COOLDOWN_SECONDS = int(os.getenv("VPN_COOLDOWN_SECONDS", "10"))


def run_vpn_server_balancer() -> None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        active_map = get_active_users_map(db)
        servers = db.execute(
            text(
                """
                SELECT id, previous_active, cooldown_until
                FROM servers
                ORDER BY id ASC
                """
            )
        ).mappings().all()

        if not servers:
            return

        batch_params: list[dict] = []
        for server in servers:
            sid = int(server["id"])
            previous_active = int(server.get("previous_active") or 0)
            active = int(active_map.get(sid, 0))

            if MAX_CONNECTIONS > 0:
                load = float(active) / float(MAX_CONNECTIONS)
            else:
                load = 0.0
            load = max(0.0, load)
            score = calculate_score(load)

            cooldown_until = server.get("cooldown_until")
            if check_spike(active, previous_active, threshold=SPIKE_THRESHOLD):
                cooldown_until = now + timedelta(seconds=COOLDOWN_SECONDS)

            batch_params.append(
                {
                    "id": sid,
                    "load": load,
                    "score": score,
                    "previous_active": active,
                    "cooldown_until": cooldown_until,
                    "updated_at": now,
                }
            )

        db.execute(
            text(
                """
                UPDATE servers
                SET
                    load = :load,
                    score = :score,
                    previous_active = :previous_active,
                    cooldown_until = :cooldown_until,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            batch_params,
        )
        db.commit()
        logger.info("vpn_server_balancer: rows_updated=%s", len(batch_params))
    except Exception:
        logger.exception("vpn_server_balancer: failed")
        db.rollback()
    finally:
        db.close()

