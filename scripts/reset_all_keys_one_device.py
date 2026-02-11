"""
Всем подпискам: allowed_devices=1, сброс флагов, перегенерация UUID.
Даты (expires_at) и пользователи не меняются. Пользователей из БД не удаляем.

Запуск на сервере: cd /opt/krotray && source venv/bin/activate && python scripts/reset_all_keys_one_device.py
"""
import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update
from api.xray_grpc import add_user_to_xray, remove_user_from_xray
from bot.config import XRAY_INBOUND_TAG
from db.models import Server, Subscription, User
from db.session import SessionLocal


def main():
    db = SessionLocal()
    try:
        # 1. Всем подпискам выставить 1 устройство и сбросить флаги
        db.execute(
            update(Subscription).values(
                allowed_devices=1,
                disabled_by_limit=False,
                violation_count=0,
            )
        )
        db.commit()
        print("Все подписки: allowed_devices=1, флаги сброшены.")

        # 2. Активные подписки с ключом — перегенерировать UUID
        subs = db.execute(
            select(Subscription, User)
            .join(User, Subscription.user_id == User.id)
            .where(Subscription.status == "active")
            .where(Subscription.uuid.isnot(None))
            .where(Subscription.server_id.isnot(None))
        ).all()

        if not subs:
            print("Нет активных подписок с ключом для перегенерации.")
            return 0

        print(f"Перегенерация ключей для {len(subs)} подписок...")
        for sub, user in subs:
            server_row = db.execute(select(Server).where(Server.id == sub.server_id)).scalar_one_or_none()
            if not server_row:
                print(f"  @{user.username or '-'} (sub_id={sub.id}): сервер не найден, пропуск")
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
                print(f"  @{user.username or '-'}: RemoveUser (продолжаем): {e}")
            try:
                add_user_to_xray(
                    host=server_row.host,
                    grpc_port=server_row.grpc_port,
                    user_uuid=new_uuid,
                    email=email,
                    inbound_tag=XRAY_INBOUND_TAG,
                )
                server_row.active_users += 1
            except Exception as e:
                print(f"  @{user.username or '-'}: AddUser ошибка: {e}")
                db.rollback()
                return 1
            sub.uuid = new_uuid
            sub.allowed_devices = 1
            sub.disabled_by_limit = False
            sub.violation_count = 0
            db.add(sub)
            db.add(server_row)
            print(f"  @{user.username or '-'} (user_id={user.id}): {old_uuid[:8]}... -> {new_uuid[:8]}...")

        db.commit()
        print("Готово. У всех allowed_devices=1, ключи новые. Пользователям заново скопировать ключ в личном кабинете.")
    except Exception as e:
        db.rollback()
        print(f"Ошибка: {e}")
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
