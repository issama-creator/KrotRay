"""
Удалить одну подписку по UUID (например просроченную из вывода check_payment.py).

Запуск: python scripts/delete_subscription.py a15c611f-e368-4fb5-9909-16406e188378
    или: python scripts/delete_subscription.py --uuid a15c611f-e368-4fb5-9909-16406e188378
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from db.models import Subscription, User
from db.session import SessionLocal


def main():
    parser = argparse.ArgumentParser(description="Удалить одну подписку по UUID")
    parser.add_argument("uuid", nargs="?", help="UUID подписки (из check_payment.py)")
    parser.add_argument("--uuid", dest="uuid_arg", metavar="UUID", help="Или передать как --uuid ...")
    args = parser.parse_args()

    uuid = args.uuid or args.uuid_arg
    if not uuid or not uuid.strip():
        parser.error("Укажи UUID подписки (например a15c611f-e368-4fb5-9909-16406e188378)")

    uuid = uuid.strip()
    db = SessionLocal()
    try:
        sub_row = db.execute(select(Subscription, User).join(User, Subscription.user_id == User.id).where(Subscription.uuid == uuid)).first()
        if not sub_row:
            print("Подписка с таким UUID не найдена")
            return 1

        sub, user = sub_row
        print(f"Подписка: id={sub.id} uuid={sub.uuid} status={sub.status}")
        print(f"Пользователь: telegram_id={user.telegram_id} @{user.username or '-'}")
        db.delete(sub)
        db.commit()
        print("Подписка удалена из БД.")
    except Exception as e:
        db.rollback()
        print(f"Ошибка: {e}")
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
