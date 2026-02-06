"""
Показать все UUID, добавленные в Xray (из нашей БД).
Активные подписки — кто сейчас в Xray. Опционально и просроченные.

Запуск: python scripts/list_xray_users.py
    или: python scripts/list_xray_users.py --all
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, desc
from db.models import Server, Subscription, User
from db.session import SessionLocal


def main():
    parser = argparse.ArgumentParser(description="Список UUID в Xray (из БД)")
    parser.add_argument("--all", action="store_true", help="Показать и просроченные подписки")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        q = (
            select(Subscription, User, Server)
            .join(User, Subscription.user_id == User.id)
            .outerjoin(Server, Subscription.server_id == Server.id)
            .order_by(desc(Subscription.created_at))
        )
        if not args.all:
            q = q.where(Subscription.status == "active").where(Subscription.uuid.isnot(None))
        rows = db.execute(q).all()

        if not rows:
            print("Нет подписок" if args.all else "Нет активных подписок с ключом")
            return 0

        print("=== UUID в Xray (из БД) ===")
        for sub, user, server in rows:
            srv = f"{server.host}:{server.grpc_port}" if server else "-"
            print(f"  {sub.uuid}  |  @{user.username or '-'}  user_id={user.id}  email=user_{user.id}")
            print(f"    status={sub.status}  expires={sub.expires_at}  server={srv}")
        print(f"\nВсего: {len(rows)}")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
