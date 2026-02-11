"""
Показать текущее количество подключений (IP) по активным подпискам.
То, что считает Xray GetStatsOnlineIpList — сколько устройств онлайн у каждого user_X.

Запуск: python scripts/check_connections.py
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from db.models import Server, Subscription
from db.session import SessionLocal
from services.xray_client import get_connections


def main():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rows = db.execute(
            select(Subscription, Server)
            .join(Server, Subscription.server_id == Server.id)
            .where(Subscription.status == "active")
            .where(Subscription.expires_at > now)
            .where(Subscription.uuid.isnot(None))
            .where(Subscription.server_id.isnot(None))
        ).all()

        if not rows:
            print("Нет активных подписок с сервером.")
            return 0

        print(f"\nПодключения (IP) по подпискам — {len(rows)} шт.\n")
        print(f"{'sub_id':<8} {'email':<12} {'connections':<12} {'allowed':<8} {'server'}")
        print("-" * 55)

        for sub, srv in rows:
            email = f"user_{sub.user_id}"
            c = get_connections(srv.host, srv.grpc_port, email)
            print(f"{sub.id:<8} {email:<12} {c:<12} {sub.allowed_devices:<8} {srv.host}:{srv.grpc_port}")

        print("-" * 55)
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
