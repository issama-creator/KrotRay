"""
Перевыдать ключи пользователям с активной подпиской.
Старый UUID удаляется из Xray, добавляется новый, в БД обновляется subscription.uuid.
После запуска пользователям нужно заново скопировать ключ в личном кабинете.

Запуск: python scripts/regenerate_keys.py --all
    или: python scripts/regenerate_keys.py islam_tsoro
    или: python scripts/regenerate_keys.py --telegram-id 1681564465
"""
import argparse
import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from api.xray_grpc import add_user_to_xray, remove_user_from_xray
from bot.config import XRAY_INBOUND_TAG
from db.models import Server, Subscription, User
from db.session import SessionLocal


def main():
    parser = argparse.ArgumentParser(description="Перевыдать ключи пользователям")
    parser.add_argument("username", nargs="?", help="Username (без @) для одного пользователя")
    parser.add_argument("--all", action="store_true", help="Все с активной подпиской")
    parser.add_argument("--telegram-id", type=int, help="Или telegram_id для одного пользователя")
    args = parser.parse_args()

    if not args.all and not args.username and not args.telegram_id:
        parser.error("Укажи --all, username или --telegram-id")

    db = SessionLocal()
    try:
        if args.all:
            subs = db.execute(
                select(Subscription, User)
                .join(User, Subscription.user_id == User.id)
                .where(Subscription.status == "active")
                .where(Subscription.uuid.isnot(None))
                .where(Subscription.server_id.isnot(None))
            ).all()
            if not subs:
                print("Нет активных подписок с ключом")
                return 0
        else:
            if args.telegram_id:
                user_row = db.execute(select(User).where(User.telegram_id == args.telegram_id)).scalar_one_or_none()
            else:
                user_row = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
            if not user_row:
                print("Пользователь не найден")
                return 1
            subs = db.execute(
                select(Subscription, User)
                .join(User, Subscription.user_id == User.id)
                .where(Subscription.user_id == user_row.id)
                .where(Subscription.status == "active")
                .where(Subscription.uuid.isnot(None))
                .where(Subscription.server_id.isnot(None))
            ).all()
            if not subs:
                print("Нет активной подписки с ключом")
                return 1

        for sub, user in subs:
            server_row = db.execute(select(Server).where(Server.id == sub.server_id)).scalar_one_or_none()
            if not server_row:
                print(f"  @{user.username or '-'} (id={sub.id}): сервер не найден, пропуск")
                continue
            email = f"user_{user.id}"
            old_uuid = sub.uuid
            new_uuid = str(uuid4())
            try:
                remove_user_from_xray(
                    host=server_row.host,
                    grpc_port=server_row.grpc_port,
                    email=email,
                    inbound_tag=XRAY_INBOUND_TAG,
                )
                server_row.active_users = max(0, server_row.active_users - 1)
            except Exception as e:
                print(f"  @{user.username or '-'}: RemoveUser ошибка (продолжаем): {e}")
            try:
                add_user_to_xray(
                    host=server_row.host,
                    grpc_port=server_row.grpc_port,
                    user_uuid=new_uuid,
                    email=email,
                    inbound_tag=XRAY_INBOUND_TAG,
                    limit_ip=1,
                )
                server_row.active_users += 1
            except Exception as e:
                print(f"  @{user.username or '-'}: AddUser ошибка: {e}")
                db.rollback()
                return 1
            sub.uuid = new_uuid
            db.add(sub)
            db.add(server_row)
            print(f"  @{user.username or '-'} (user_id={user.id}): {old_uuid[:8]}... -> {new_uuid[:8]}...")

        db.commit()
        print("Готово. Пользователям нужно заново скопировать ключ в личном кабинете.")
    except Exception as e:
        db.rollback()
        print(f"Ошибка: {e}")
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
