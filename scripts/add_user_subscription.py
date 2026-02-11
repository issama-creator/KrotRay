"""
Добавить пользователя в БД и выдать подписку.
По username (ник в Telegram) или telegram_id. Срок — дни и часы.

Если пользователя нет в БД — нужен --telegram-id для создания.

Запуск: python scripts/add_user_subscription.py username --days 30
    или: python scripts/add_user_subscription.py username --minutes 30
    или: python scripts/add_user_subscription.py username --days 28 --hours 12
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
    parser = argparse.ArgumentParser(description="Добавить пользователя и подписку")
    parser.add_argument("username", nargs="?", help="Username в Telegram (без @)")
    parser.add_argument("--username", dest="username_flag", help="Username (альтернатива позиционному аргументу)")
    parser.add_argument("--telegram-id", type=int, help="telegram_id (обязательно для нового пользователя)")
    parser.add_argument("--first-name", type=str, help="Имя (для нового пользователя)")
    parser.add_argument("--days", type=int, default=0, help="Срок подписки: дней")
    parser.add_argument("--hours", type=int, default=0, help="Срок подписки: часов")
    parser.add_argument("--minutes", type=int, default=0, help="Срок подписки: минут")
    args = parser.parse_args()

    username = args.username or args.username_flag
    if not username and not args.telegram_id:
        parser.error("Укажи username или --telegram-id")

    if args.days == 0 and args.hours == 0 and args.minutes == 0:
        parser.error("Укажи --days, --hours и/или --minutes (срок подписки)")

    db = SessionLocal()
    try:
        user = None
        if username:
            user_row = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
            if user_row:
                user = user_row
        if not user and args.telegram_id:
            user_row = db.execute(select(User).where(User.telegram_id == args.telegram_id)).scalar_one_or_none()
            if user_row:
                user = user_row

        if not user:
            if args.telegram_id:
                user = User(
                    telegram_id=args.telegram_id,
                    username=username or None,
                    first_name=args.first_name or None,
                )
                db.add(user)
                db.flush()
                print(f"Создан пользователь: id={user.id} telegram_id={user.telegram_id} username=@{user.username or '-'}")
            else:
                print("Пользователь не найден. Для создания укажи --telegram-id")
                return 1
        else:
            print(f"User: id={user.id} telegram_id={user.telegram_id} username=@{user.username or '-'}")

        total_seconds = args.days * 86400 + args.hours * 3600 + args.minutes * 60
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=total_seconds)

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
            tariff_months=1,
            uuid=sub_uuid,
            server_id=server.id,
            allowed_devices=1,
        )
        db.add(sub)
        db.commit()

        print(f"Подписка создана: uuid={sub_uuid}")
        dur = []
        if args.days: dur.append(f"{args.days} дн.")
        if args.hours: dur.append(f"{args.hours} ч.")
        if args.minutes: dur.append(f"{args.minutes} мин.")
        print(f"  Срок: {' '.join(dur)} -> expires_at={expires_at}")
        print(f"  Сервер: {server.name} ({server.host}:{server.grpc_port})")
        print("Пользователю нужно скопировать ключ в личном кабинете.")
    except Exception as e:
        db.rollback()
        print(f"Ошибка: {e}")
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
