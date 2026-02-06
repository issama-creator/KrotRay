"""
Удалить подписку и платежи пользователя (как будто не платил).
Перед оплатой удаляет из Xray, в БД — subscription и payments.

Запуск: python scripts/delete_user_subscription.py islam_tsoro
    или: python scripts/delete_user_subscription.py --telegram-id 1681564465
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, delete
from api.xray_grpc import remove_user_from_xray
from bot.config import XRAY_INBOUND_TAG
from db.models import Payment, Server, Subscription, User
from db.session import SessionLocal


def main():
    parser = argparse.ArgumentParser(description="Удалить подписку и платежи пользователя")
    parser.add_argument("username", nargs="?", help="Username (без @), например islam_tsoro")
    parser.add_argument("--telegram-id", type=int, help="Или telegram_id")
    parser.add_argument("--no-payments", action="store_true", help="Не удалять платежи (только подписку)")
    args = parser.parse_args()

    if not args.username and not args.telegram_id:
        parser.error("Укажи username или --telegram-id")

    db = SessionLocal()
    try:
        if args.telegram_id:
            user_row = db.execute(select(User).where(User.telegram_id == args.telegram_id)).scalar_one_or_none()
        else:
            user_row = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()

        if not user_row:
            print("Пользователь не найден")
            return 1

        user = user_row
        print(f"User: id={user.id} telegram_id={user.telegram_id} username=@{user.username or '-'}")

        # Подписки
        subs = db.execute(select(Subscription).where(Subscription.user_id == user.id)).scalars().all()
        for sub in subs:
            if sub.server_id and sub.uuid:
                server_row = db.execute(select(Server).where(Server.id == sub.server_id)).scalar_one_or_none()
                if server_row:
                    email = f"user_{user.id}"
                    try:
                        remove_user_from_xray(
                            host=server_row.host,
                            grpc_port=server_row.grpc_port,
                            email=email,
                            inbound_tag=XRAY_INBOUND_TAG,
                        )
                        server_row.active_users = max(0, server_row.active_users - 1)
                        db.add(server_row)
                        print(f"  Удалён из Xray: server={server_row.host}:{server_row.grpc_port} email={email}")
                    except Exception as e:
                        print(f"  Ошибка RemoveUser: {e}")
            db.delete(sub)
            print(f"  Подписка id={sub.id} удалена")

        # Платежи
        if not args.no_payments:
            deleted = db.execute(delete(Payment).where(Payment.user_id == user.id))
            print(f"  Платежей удалено: {deleted.rowcount}")

        db.commit()
        print("Готово. Пользователь может заново оплатить.")
    except Exception as e:
        db.rollback()
        print(f"Ошибка: {e}")
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
