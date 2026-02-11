"""
Показать текущее количество подключений (IP) по активным подпискам.
То, что считает Xray GetStatsOnlineIpList — сколько устройств онлайн у каждого user_X.

Запуск: python scripts/check_connections.py
        python scripts/check_connections.py --debug   # + список онлайн из Xray (формат name)
        python scripts/check_connections.py --ips     # для каждого user показать IP и время
        python scripts/check_connections.py --uuid c8e59e9b-7d1f-424f-9440-e464b2a9fdd1   # только этот ключ
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from db.models import Server, Subscription
from db.session import SessionLocal
from services.xray_client import get_connections, get_all_online_users, get_online_ips


def main():
    parser = argparse.ArgumentParser(description="Показать connections по подпискам")
    parser.add_argument("--debug", action="store_true", help="Показать список онлайн-пользователей из Xray (формат name)")
    parser.add_argument("--ips", action="store_true", help="Показать для каждого user список IP и время последней активности")
    parser.add_argument("--uuid", type=str, help="Проверить только подписку с этим UUID ключа")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        if args.uuid:
            row = db.execute(
                select(Subscription, Server)
                .join(Server, Subscription.server_id == Server.id)
                .where(Subscription.uuid == args.uuid.strip())
            ).first()
            if not row:
                print(f"Подписка с UUID {args.uuid!r} не найдена.")
                return 1
            rows = [row]
        else:
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

        if args.debug and rows:
            sub0, srv0 = rows[0]
            online = get_all_online_users(srv0.host, srv0.grpc_port)
            print(f"\n[Xray GetAllOnlineUsers] {srv0.host}:{srv0.grpc_port} → {online!r}\n")

        print(f"\nПодключения (IP) по подпискам — {len(rows)} шт." + ("\n" if not args.uuid else f" (UUID: {args.uuid})\n"))
        print(f"{'sub_id':<8} {'email':<12} {'connections':<12} {'allowed':<8} {'server'}")
        print("-" * 55)

        for sub, srv in rows:
            email = f"user_{sub.user_id}"
            c = get_connections(srv.host, srv.grpc_port, email)
            print(f"{sub.id:<8} {email:<12} {c:<12} {sub.allowed_devices:<8} {srv.host}:{srv.grpc_port}")
            if args.ips and c > 0:
                ips_map = get_online_ips(srv.host, srv.grpc_port, email)
                for ip, ts in ips_map.items():
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "—"
                    print(f"           → {ip}  (последняя активность: {dt})")

        print("-" * 55)
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
