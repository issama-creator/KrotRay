"""
Полностью удалить пользователя: из Xray (RemoveUser) и из БД (user + подписки + платежи).
После этого можно заново добавить через add_user_subscription.py с --telegram-id.

Запуск: python scripts/remove_user_completely.py islamtsoro
    или: python scripts/remove_user_completely.py --telegram-id 123456789
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from api.xray_grpc import remove_user_from_xray
from bot.config import XRAY_INBOUND_TAG
from db.models import Server, Subscription, User
from db.session import SessionLocal


def main():
    parser = argparse.ArgumentParser(description="Полностью удалить пользователя из Xray и БД")
    parser.add_argument("username", nargs="?", help="Username в Telegram (без @), например islamtsoro")
    parser.add_argument("--telegram-id", type=int, help="Или telegram_id")
    args = parser.parse_args()

    if not args.username and not args.telegram_id:
        parser.error("Укажи username или --telegram-id")

    db = SessionLocal()
    try:
        if args.telegram_id:
            user = db.execute(select(User).where(User.telegram_id == args.telegram_id)).scalar_one_or_none()
        else:
            user = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
            if not user and "_" in args.username:
                user = db.execute(select(User).where(User.username == args.username.replace("_", ""))).scalar_one_or_none()

        if not user:
            print("Пользователь не найден")
            return 1

        print(f"User: id={user.id} telegram_id={user.telegram_id} username=@{user.username or '-'}")

        subs = db.execute(select(Subscription).where(Subscription.user_id == user.id)).scalars().all()
        email = f"user_{user.id}"
        for sub in subs:
            if sub.server_id and sub.uuid:
                srv = db.execute(select(Server).where(Server.id == sub.server_id)).scalar_one_or_none()
                if srv:
                    try:
                        remove_user_from_xray(
                            host=srv.host,
                            grpc_port=srv.grpc_port,
                            email=email,
                            inbound_tag=XRAY_INBOUND_TAG,
                        )
                        srv.active_users = max(0, srv.active_users - 1)
                        db.add(srv)
                        print(f"  Удалён из Xray: {srv.host}:{srv.grpc_port} email={email}")
                    except Exception as e:
                        print(f"  Ошибка RemoveUser: {e}")

        saved_telegram_id = user.telegram_id
        saved_username = user.username or args.username or "USERNAME"
        db.delete(user)
        db.commit()
        print(f"  Удалён из БД: user id={user.id}, подписки и платежи (CASCADE)")
        print("Готово. Чтобы добавить снова с 1 устройством:")
        print(f"  python scripts/add_user_subscription.py {saved_username} --telegram-id {saved_telegram_id} --days 30")
    except Exception as e:
        db.rollback()
        print(f"Ошибка: {e}")
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
