"""
Восстановить подписку пользователю (после случайного удаления).
Создаёт новую подписку, добавляет в Xray, выдаёт новый ключ.

Запуск: python scripts/restore_user_subscription.py hexaminity
    или: python scripts/restore_user_subscription.py --telegram-id 5360248046
    или: python scripts/restore_user_subscription.py hexaminity --expires 2026-03-08
"""
import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from api.server import get_least_loaded_server
from api.xray_grpc import add_user_to_xray
from bot.config import XRAY_INBOUND_TAG
from db.models import Server, Subscription, User
from db.session import SessionLocal


def main():
    parser = argparse.ArgumentParser(description="Восстановить подписку пользователю")
    parser.add_argument("username", nargs="?", help="Username (без @)")
    parser.add_argument("--telegram-id", type=int, help="Или telegram_id")
    parser.add_argument("--expires", metavar="YYYY-MM-DD", help="Дата окончания подписки")
    parser.add_argument("--days", type=int, help="Подписка на N дней (например --days 28)")
    parser.add_argument("--months", type=int, default=1, choices=[1, 3], help="Тариф: 1 или 3 месяца (если нет --days/--expires)")
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

        if args.expires:
            try:
                expires_at = datetime.strptime(args.expires.strip(), "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59, tzinfo=timezone.utc
                )
            except ValueError:
                print("Неверный формат --expires, используй YYYY-MM-DD")
                return 1
        elif args.days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=args.days)
        else:
            expires_at = datetime.now(timezone.utc) + timedelta(days=30 * args.months)

        server = get_least_loaded_server(db)
        if not server:
            print("Нет доступного сервера Xray")
            return 1

        sub_uuid = str(uuid4())
        email = f"user_{user.id}"
        try:
            add_user_to_xray(
                host=server.host,
                grpc_port=server.grpc_port,
                user_uuid=sub_uuid,
                email=email,
                inbound_tag=XRAY_INBOUND_TAG,
            )
            server.active_users += 1
            db.add(server)
        except Exception as e:
            print(f"Ошибка AddUser: {e}")
            return 1

        sub = Subscription(
            user_id=user.id,
            status="active",
            expires_at=expires_at,
            tariff_months=args.months,
            uuid=sub_uuid,
            server_id=server.id,
        )
        db.add(sub)
        db.commit()

        print(f"Подписка создана: uuid={sub_uuid}")
        print(f"  expires_at={expires_at}")
        print(f"  server={server.name} ({server.host}:{server.grpc_port})")
        print("Пользователю нужно скопировать новый ключ в личном кабинете.")
    except Exception as e:
        db.rollback()
        print(f"Ошибка: {e}")
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
