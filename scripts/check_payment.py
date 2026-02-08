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

from sqlalchemy import select, desc, func
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

        # Без периода: сводка по подпискам и последние платежи/подписки
        total = db.execute(select(func.count(Subscription.id))).scalar() or 0
        active = db.execute(select(func.count(Subscription.id)).where(Subscription.status == "active")).scalar() or 0
        expired = db.execute(select(func.count(Subscription.id)).where(Subscription.status == "expired")).scalar() or 0

        def _dt(d):
            if d is None:
                return "-"
            return d.strftime("%Y-%m-%d %H:%M") if hasattr(d, "strftime") else str(d)

        # Сводка подписок — таблица
        print("┌" + "─" * 42 + "┐")
        print("│  ПОДПИСКИ (сводка)" + " " * 22 + "│")
        print("├" + "─" * 42 + "┤")
        print(f"│  Всего подписок:   {total:>6}              │")
        print(f"│  Активных:         {active:>6}              │")
        print(f"│  Просроченных:     {expired:>6}              │")
        print("└" + "─" * 42 + "┘")
        print()

        payments = db.execute(
            select(Payment, User)
            .join(User, Payment.user_id == User.id)
            .order_by(desc(Payment.created_at))
            .limit(30)
        ).all()

        # Таблица платежей
        w_date = 16
        w_tg = 14
        w_user = 14
        w_sum = 8
        w_status = 12
        w_tariff = 6
        sep_len = w_date + w_tg + w_user + w_sum + w_status + w_tariff + 12
        sep = "─" * sep_len
        print("┌" + sep + "┐")
        print("│  ПОСЛЕДНИЕ ПЛАТЕЖИ" + " " * (sep_len - 21) + "│")
        print("├" + "─" * w_date + "┬" + "─" * w_tg + "┬" + "─" * w_user + "┬" + "─" * w_sum + "┬" + "─" * w_status + "┬" + "─" * w_tariff + "┤")
        print(f"│  {'Дата':<{w_date-2}} │ {'telegram_id':<{w_tg-2}} │ {'username':<{w_user-2}} │ {'Сумма':<{w_sum-2}} │ {'Статус':<{w_status-2}} │ {'Тариф':<{w_tariff-2}} │")
        print("├" + "─" * w_date + "┼" + "─" * w_tg + "┼" + "─" * w_user + "┼" + "─" * w_sum + "┼" + "─" * w_status + "┼" + "─" * w_tariff + "┤")
        for p, u in payments:
            user = f"@{u.username or '-'}"[: w_user - 2]
            print(f"│  {_dt(p.created_at):<{w_date-2}} │ {str(u.telegram_id):<{w_tg-2}} │ {user:<{w_user-2}} │ {str(p.amount):<{w_sum-2}} │ {p.status:<{w_status-2}} │ {str(p.tariff_months):<{w_tariff-2}} │")
        print("└" + "─" * w_date + "┴" + "─" * w_tg + "┴" + "─" * w_user + "┴" + "─" * w_sum + "┴" + "─" * w_status + "┴" + "─" * w_tariff + "┘")
        print()

        subs = db.execute(
            select(Subscription, User)
            .join(User, Subscription.user_id == User.id)
            .order_by(desc(Subscription.created_at))
            .limit(30)
        ).all()

        # Таблица подписок
        w_uuid = 38
        w_exp = 16
        sep2_len = w_date + w_tg + w_user + w_uuid + w_status + w_exp + 12
        sep2 = "─" * sep2_len
        print("┌" + sep2 + "┐")
        print("│  ПОСЛЕДНИЕ ПОДПИСКИ" + " " * (sep2_len - 22) + "│")
        print("├" + "─" * w_date + "┬" + "─" * w_tg + "┬" + "─" * w_user + "┬" + "─" * w_uuid + "┬" + "─" * w_status + "┬" + "─" * w_exp + "┤")
        print(f"│  {'Дата':<{w_date-2}} │ {'telegram_id':<{w_tg-2}} │ {'username':<{w_user-2}} │ {'uuid':<{w_uuid-2}} │ {'Статус':<{w_status-2}} │ {'Истекает':<{w_exp-2}} │")
        print("├" + "─" * w_date + "┼" + "─" * w_tg + "┼" + "─" * w_user + "┼" + "─" * w_uuid + "┼" + "─" * w_status + "┼" + "─" * w_exp + "┤")
        for s, u in subs:
            user = f"@{u.username or '-'}"[: w_user - 2]
            uuid_short = (s.uuid or "-")[: w_uuid - 2] if s.uuid else "-"
            print(f"│  {_dt(s.created_at):<{w_date-2}} │ {str(u.telegram_id):<{w_tg-2}} │ {user:<{w_user-2}} │ {uuid_short:<{w_uuid-2}} │ {s.status:<{w_status-2}} │ {_dt(s.expires_at):<{w_exp-2}} │")
        print("└" + "─" * w_date + "┴" + "─" * w_tg + "┴" + "─" * w_user + "┴" + "─" * w_uuid + "┴" + "─" * w_status + "┴" + "─" * w_exp + "┘")
    finally:
        db.close()


if __name__ == "__main__":
    main()
