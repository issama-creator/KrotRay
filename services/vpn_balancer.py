from __future__ import annotations

from datetime import datetime, timezone
import random

from sqlalchemy import text
from sqlalchemy.orm import Session


def calculate_score(load: float) -> float:
    return float(load) ** 1.2


def check_spike(active: int, previous_active: int, threshold: int = 20) -> bool:
    return int(active) - int(previous_active) > int(threshold)


def apply_cooldown(weight: float, cooldown_until: datetime | None, now: datetime) -> float:
    adjusted = float(weight)
    if cooldown_until is not None:
        cmp_now = now
        if cooldown_until.tzinfo is None and now.tzinfo is not None:
            cmp_now = now.replace(tzinfo=None)
        elif cooldown_until.tzinfo is not None and now.tzinfo is None:
            cmp_now = now.replace(tzinfo=cooldown_until.tzinfo)
        if cmp_now < cooldown_until:
            adjusted *= 0.3
    return adjusted


def calculate_weight(server: dict, now: datetime) -> float:
    score = float(server.get("score", 0.0) or 0.0)
    load = float(server.get("load", 0.0) or 0.0)
    cooldown_until = server.get("cooldown_until")

    free_ratio = 1.0 - load
    base = 1.0 / (score + 0.01)
    capacity = free_ratio ** 2
    weight = base * capacity
    return apply_cooldown(weight, cooldown_until, now)


def get_active_users_map(db: Session) -> dict[int, int]:
    """
    Returns active users grouped by server_id from live edge sessions.

    Output example:
        {1: 120, 2: 87}
    """
    rows = db.execute(
        text(
            """
            SELECT server_id, COUNT(*)::int AS active
            FROM edge_sessions
            WHERE stopped_at IS NULL
              AND expires_at > NOW()
            GROUP BY server_id
            """
        )
    ).mappings().all()
    return {int(row["server_id"]): int(row["active"]) for row in rows}


def get_candidate_servers(db: Session) -> list[dict]:
    top_20 = [
        dict(row)
        for row in db.execute(
            text(
                """
                SELECT
                    id,
                    host,
                    status,
                    load,
                    score,
                    previous_active,
                    cooldown_until,
                    updated_at
                FROM servers
                ORDER BY score ASC, id ASC
                LIMIT 20
                """
            )
        ).mappings().all()
    ]

    filtered = [
        s
        for s in top_20
        if (s.get("status") == "alive")
        and float(s.get("load", 0.0) or 0.0) < 0.9
        and (1.0 - float(s.get("load", 0.0) or 0.0)) > 0.1
    ]

    if len(filtered) >= 4:
        return filtered

    if not top_20:
        return []

    if len(filtered) == 0:
        return top_20[:4]

    return random.sample(top_20, k=min(4, len(top_20)))


def weighted_sample(servers: list[dict], k: int = 4) -> list[dict]:
    if not servers or k <= 0:
        return []

    now = datetime.now(timezone.utc)
    pool = list(servers)
    picked: list[dict] = []

    while pool and len(picked) < k:
        weights = [max(0.0, calculate_weight(s, now)) for s in pool]
        if sum(weights) <= 0:
            left = k - len(picked)
            picked.extend(random.sample(pool, k=min(left, len(pool))))
            break
        chosen = random.choices(pool, weights=weights, k=1)[0]
        picked.append(chosen)
        pool = [s for s in pool if s.get("id") != chosen.get("id")]

    return picked

