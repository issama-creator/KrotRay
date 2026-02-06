"""
Проверка оплат и подписок в БД (только модели, без сырого SQL).
Запуск из корня: python scripts/check_payment.py
                 python scripts/check_payment.py --from 2025-01-01 --to 2025-01-31

Без аргументов — последние платежи и подписки.
С --from и --to — только кто оплатил в этом периоде (status=completed).
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, desc
from db.models import Payment, Subscription, User
from db.session import SessionLocal


def parse_date(s: str) -> datetime:
    """'2025-01-15' -> datetime начало дня UTC."""
    dt = datetime.strptime(s.strip(), "%Y-%m-%d")
    return dt.replace(tzinfo=timezone.utc)


def main():
    parser = argparse.ArgumentParser(description="Кто оплатил за период (по моделям)")
    parser.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", help="Начало периода")
    parser.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", help="Конец периода (включительно, конец дня)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.date_from and args.date_to:
            date_from = parse_date(args.date_from)
            date_to = parse_date(args.date_to)
            # Конец дня
            date_to = date_to.replace(hour=23, minute=59, second=59, microsecond=999999)
            # Только оплаченные (completed) в этом периоде
            rows = (
                db.execute(
                    select(Payment, User)
                    .join(User, Payment.user_id == User.id)
                    .where(Payment.status == "completed")
                    .where(Payment.created_at >= date_from)
                    .where(Payment.created_at <= date_to)
                    .order_by(Payment.created_at.asc())
                )
            ).all()
            print(f"=== Оплатили с {args.date_from} по {args.date_to} (всего {len(rows)}) ===")
            for p, u in rows:
                print(f"  {p.created_at}  telegram_id={u.telegram_id}  @{u.username or '-'}  {u.first_name or '-'}  {p.amount} ₽  {p.tariff_months} мес.")
            return

        # Без периода: последние платежи и подписки
        payments = db.execute(
            select(Payment, User)
            .join(User, Payment.user_id == User.id)
            .order_by(desc(Payment.created_at))
            .limit(30)
        ).all()
        print("=== Последние платежи (payments) ===")
        for p, u in payments:
            print(f"  {p.created_at}  telegram_id={u.telegram_id}  @{u.username or '-'}  {p.amount}  status={p.status}  tariff={p.tariff_months} мес.")

        subs = db.execute(
            select(Subscription, User)
            .join(User, Subscription.user_id == User.id)
            .order_by(desc(Subscription.created_at))
            .limit(30)
        ).all()
        print("\n=== Последние подписки (subscriptions) ===")
        for s, u in subs:
            print(f"  {s.created_at}  telegram_id={u.telegram_id}  @{u.username or '-'}  uuid={s.uuid or '-'}  status={s.status}  expires={s.expires_at}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
