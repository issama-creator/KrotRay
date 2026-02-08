"""
Продлить подписку пользователю. Работает для активной и просроченной.
- Активная: добавляет время к текущему expires_at.
- Просроченная: переиспользуем тот же UUID (пользователь уже в Xray), продлеваем в БД.

Запуск: python scripts/extend_subscription.py username --days 30
    или: python scripts/extend_subscription.py username --days 7 --hours 12 --minutes 30
    или: python scripts/extend_subscription.py --telegram-id 123456 --minutes 60
"""
import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, desc
from api.server import get_least_loaded_server
from api.xray_grpc import add_user_to_xray, remove_user_from_xray
from bot.config import XRAY_INBOUND_TAG
from db.models import Server, Subscription, User
from db.session import SessionLocal


def main():
    parser = argparse.ArgumentParser(description="Продлить подписку")
    parser.add_argument("username", nargs="?", help="Username (без @)")
    parser.add_argument("--username", dest="username_flag", help="Username (альтернатива)")
    parser.add_argument("--telegram-id", type=int, help="Или telegram_id")
    parser.add_argument("--days", type=int, default=0, help="Добавить дней")
    parser.add_argument("--hours", type=int, default=0, help="Добавить часов")
    parser.add_argument("--minutes", type=int, default=0, help="Добавить минут")
    parser.add_argument("--set-duration", action="store_true", help="Поставить срок от СЕЙЧАС (не добавлять к текущему)")
    args = parser.parse_args()

    username = args.username or args.username_flag
    if not username and not args.telegram_id:
        parser.error("Укажи username или --telegram-id")

    if args.days == 0 and args.hours == 0 and args.minutes == 0:
        parser.error("Укажи --days, --hours и/или --minutes")

    duration_seconds = args.days * 86400 + args.hours * 3600 + args.minutes * 60

    db = SessionLocal()
    try:
        if args.telegram_id:
            user_row = db.execute(select(User).where(User.telegram_id == args.telegram_id)).scalar_one_or_none()
        else:
            user_row = db.execute(select(User).where(User.username == username)).scalar_one_or_none()

        if not user_row:
            print("Пользователь не найден")
            return 1

        user = user_row
        print(f"User: id={user.id} telegram_id={user.telegram_id} username=@{user.username or '-'}")

        sub_row = (
            db.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id)
                .order_by(desc(Subscription.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if sub_row and sub_row.status == "active" and sub_row.uuid:
            sub = sub_row
            if args.set_duration:
                sub.expires_at = now + timedelta(seconds=duration_seconds)
            else:
                base = sub.expires_at.replace(tzinfo=timezone.utc) if sub.expires_at.tzinfo is None else sub.expires_at
                if base < now:
                    base = now
                sub.expires_at = base + timedelta(seconds=duration_seconds)
            db.add(sub)
            db.commit()
            dur = []
            if args.days: dur.append(f"{args.days} дн.")
            if args.hours: dur.append(f"{args.hours} ч.")
            if args.minutes: dur.append(f"{args.minutes} мин.")
            print(f"Подписка продлена: expires_at={sub.expires_at}")
        else:
            if args.set_duration:
                expires_at = now + timedelta(seconds=duration_seconds)
            else:
                if sub_row and sub_row.expires_at:
                    base = sub_row.expires_at.replace(tzinfo=timezone.utc) if sub_row.expires_at.tzinfo is None else sub_row.expires_at
                    expires_at = max(base, now) + timedelta(seconds=duration_seconds)
                else:
                    expires_at = now + timedelta(seconds=duration_seconds)

            # Просроченная/старая подписка с uuid и server_id — продлеваем тот же UUID, в Xray не лезем
            # Ищем любую подписку пользователя с uuid и server_id (на случай если последняя без server_id)
            sub_for_reuse = (
                db.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user.id)
                    .where(Subscription.uuid.isnot(None))
                    .where(Subscription.server_id.isnot(None))
                    .order_by(desc(Subscription.created_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
            if sub_for_reuse and sub_for_reuse.uuid and sub_for_reuse.server_id:
                # После истечения пользователя убрали из Xray — снова добавляем тот же UUID
                server_row = db.execute(select(Server).where(Server.id == sub_for_reuse.server_id)).scalar_one_or_none()
                if server_row:
                    try:
                        add_user_to_xray(
                            host=server_row.host,
                            grpc_port=server_row.grpc_port,
                            user_uuid=sub_for_reuse.uuid,
                            email=f"user_{user.id}",
                            inbound_tag=XRAY_INBOUND_TAG,
                            limit_ip=1,
                        )
                        server_row.active_users += 1
                        db.add(server_row)
                    except Exception as e:
                        print(f"Ошибка AddUser (тот же UUID): {e}")
                        return 1
                sub_for_reuse.status = "active"
                sub_for_reuse.expires_at = expires_at
                db.add(sub_for_reuse)
                db.commit()
                dur = []
                if args.days: dur.append(f"{args.days} дн.")
                if args.hours: dur.append(f"{args.hours} ч.")
                if args.minutes: dur.append(f"{args.minutes} мин.")
                print(f"Подписка продлена (тот же UUID): uuid={sub_for_reuse.uuid} expires_at={expires_at}")
                print("Ключ в личном кабинете не меняется — тот же ключ снова работает.")
                return 0

            server = get_least_loaded_server(db)
            if not server:
                print("Нет доступного сервера Xray")
                return 1

            sub_uuid = str(uuid4())
            email = f"user_{user.id}"
            # Если user_N уже есть в Xray (старая подписка без server_id или на другом сервере) — сначала убираем
            all_servers = list(db.execute(select(Server)).scalars().all())
            for srv in all_servers:
                try:
                    remove_user_from_xray(
                        host=srv.host,
                        grpc_port=srv.grpc_port,
                        email=email,
                        inbound_tag=XRAY_INBOUND_TAG,
                    )
                    srv.active_users = max(0, srv.active_users - 1)
                    db.add(srv)
                    db.commit()
                except Exception:
                    pass

            try:
                add_user_to_xray(
                    host=server.host,
                    grpc_port=server.grpc_port,
                    user_uuid=sub_uuid,
                    email=email,
                    inbound_tag=XRAY_INBOUND_TAG,
                    limit_ip=1,
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
            )
            db.add(sub)
            db.commit()

            dur = []
            if args.days: dur.append(f"{args.days} дн.")
            if args.hours: dur.append(f"{args.hours} ч.")
            if args.minutes: dur.append(f"{args.minutes} мин.")
            print(f"Новая подписка: uuid={sub_uuid} expires_at={expires_at}")
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
