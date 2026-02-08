"""
Передобавить пользователя в Xray с limit_ip=1 (тот же UUID, ключ не меняется).
Нужно для уже существующих юзеров, чтобы у них заработало ограничение «1 устройство».

Запуск: python scripts/set_limit_ip_user.py islam_tsoro
    или: python scripts/set_limit_ip_user.py --telegram-id 1681564465
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from api.xray_grpc import add_user_to_xray, remove_user_from_xray
from bot.config import XRAY_INBOUND_TAG
from db.models import Server, Subscription, User
from db.session import SessionLocal


def main():
    parser = argparse.ArgumentParser(
        description="Передобавить пользователя в Xray с limit_ip=1 (UUID не меняется)"
    )
    parser.add_argument("username", nargs="?", help="Username без @, например islam_tsoro")
    parser.add_argument("--telegram-id", type=int, help="Или telegram_id")
    parser.add_argument("--limit-ip", type=int, default=1, help="limit_ip (по умолчанию 1)")
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
        email = f"user_{user.id}"
        print(f"User: id={user.id} username=@{user.username or '-'} email={email} limit_ip={args.limit_ip}")

        subs = (
            db.execute(
                select(Subscription).where(
                    Subscription.user_id == user.id,
                    Subscription.uuid.isnot(None),
                    Subscription.server_id.isnot(None),
                )
            )
            .scalars().all()
        )

        if not subs:
            print("Нет подписок с uuid и server_id (нет ключа в Xray).")
            return 1

        for sub in subs:
            server_row = db.execute(select(Server).where(Server.id == sub.server_id)).scalar_one_or_none()
            if not server_row:
                print(f"  Подписка id={sub.id}: сервер не найден, пропуск")
                continue
            try:
                remove_user_from_xray(
                    host=server_row.host,
                    grpc_port=server_row.grpc_port,
                    email=email,
                    inbound_tag=XRAY_INBOUND_TAG,
                )
                server_row.active_users = max(0, server_row.active_users - 1)
                db.add(server_row)
            except Exception as e:
                print(f"  RemoveUser на {server_row.host}: {e} (продолжаем)")
            try:
                add_user_to_xray(
                    host=server_row.host,
                    grpc_port=server_row.grpc_port,
                    user_uuid=sub.uuid,
                    email=email,
                    inbound_tag=XRAY_INBOUND_TAG,
                    limit_ip=args.limit_ip,
                )
                server_row.active_users += 1
                db.add(server_row)
                print(f"  OK: server={server_row.host}:{server_row.grpc_port} uuid={sub.uuid[:8]}... limit_ip={args.limit_ip}")
            except Exception as e:
                print(f"  Ошибка AddUser: {e}")
                db.rollback()
                return 1

        db.commit()
        print("Готово. Ключ тот же, в Xray теперь limit_ip=%s." % args.limit_ip)
    except Exception as e:
        db.rollback()
        print(f"Ошибка: {e}")
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
