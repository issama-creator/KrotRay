"""
Просмотр данных из базы данных.
Использование:
    python scripts/view_db.py                    # Показать все подписки
    python scripts/view_db.py --users            # Показать всех пользователей
    python scripts/view_db.py --payments         # Показать все платежи
    python scripts/view_db.py --servers          # Показать все серверы
    python scripts/view_db.py --subscription-id 1 # Показать конкретную подписку
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from db.models import Payment, Server, Subscription, User
from db.session import SessionLocal


def format_datetime(dt):
    """Форматирование даты для вывода."""
    if not dt:
        return "—"
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


def print_subscriptions(db, subscription_id=None):
    """Вывести подписки."""
    if subscription_id:
        query = select(Subscription, User).join(User).where(Subscription.id == subscription_id)
    else:
        query = select(Subscription, User).join(User).order_by(Subscription.created_at.desc()).limit(20)
    
    results = db.execute(query).all()
    
    if not results:
        print("Подписки не найдены.")
        return
    
    print("\n" + "=" * 120)
    print(f"{'ID':<5} {'User':<20} {'Status':<10} {'UUID':<38} {'Expires':<20} {'Devices':<8} {'Disabled':<8} {'Violations':<10}")
    print("=" * 120)
    
    for sub, user in results:
        uuid_short = f"{sub.uuid[:8]}..." if sub.uuid else "—"
        username = user.username or f"id_{user.id}"
        expires_str = format_datetime(sub.expires_at)
        
        print(f"{sub.id:<5} {username:<20} {sub.status:<10} {uuid_short:<38} {expires_str:<20} "
              f"{sub.allowed_devices:<8} {str(sub.disabled_by_limit):<8} {sub.violation_count:<10}")
    
    print("=" * 120)
    print(f"\nВсего показано: {len(results)}")


def print_users(db):
    """Вывести пользователей."""
    users = db.execute(select(User).order_by(User.id.desc()).limit(50)).scalars().all()
    
    if not users:
        print("Пользователи не найдены.")
        return
    
    print("\n" + "=" * 80)
    print(f"{'ID':<5} {'Telegram ID':<15} {'Username':<25} {'First Name':<20}")
    print("=" * 80)
    
    for user in users:
        username = user.username or "—"
        first_name = user.first_name or "—"
        print(f"{user.id:<5} {user.telegram_id:<15} {username:<25} {first_name:<20}")
    
    print("=" * 80)
    print(f"\nВсего показано: {len(users)}")


def print_payments(db):
    """Вывести платежи."""
    payments = db.execute(
        select(Payment, User)
        .join(User)
        .order_by(Payment.created_at.desc())
        .limit(50)
    ).all()
    
    if not payments:
        print("Платежи не найдены.")
        return
    
    print("\n" + "=" * 100)
    print(f"{'ID':<5} {'User':<20} {'Amount':<10} {'Status':<12} {'Tariff':<8} {'Devices':<8} {'Created':<20}")
    print("=" * 100)
    
    for payment, user in payments:
        username = user.username or f"id_{user.id}"
        created_str = format_datetime(payment.created_at)
        tariff_str = f"{payment.tariff_months}м"
        
        print(f"{payment.id:<5} {username:<20} {payment.amount:<10.2f} {payment.status:<12} "
              f"{tariff_str:<8} {payment.devices:<8} {created_str:<20}")
    
    print("=" * 100)
    print(f"\nВсего показано: {len(payments)}")


def print_servers(db):
    """Вывести серверы."""
    servers = db.execute(select(Server).order_by(Server.id)).scalars().all()
    
    if not servers:
        print("Серверы не найдены.")
        return
    
    print("\n" + "=" * 100)
    print(f"{'ID':<5} {'Name':<20} {'Host':<20} {'gRPC Port':<12} {'Active Users':<15} {'Max Users':<12} {'Enabled':<8}")
    print("=" * 100)
    
    for server in servers:
        enabled_str = "✓" if server.enabled else "✗"
        print(f"{server.id:<5} {server.name:<20} {server.host:<20} {server.grpc_port:<12} "
              f"{server.active_users:<15} {server.max_users:<12} {enabled_str:<8}")
    
    print("=" * 100)
    print(f"\nВсего серверов: {len(servers)}")


def print_stats(db):
    """Вывести статистику."""
    stats = db.execute(text("""
        SELECT 
            (SELECT COUNT(*) FROM users) as total_users,
            (SELECT COUNT(*) FROM subscriptions WHERE status = 'active') as active_subs,
            (SELECT COUNT(*) FROM subscriptions WHERE status = 'expired') as expired_subs,
            (SELECT COUNT(*) FROM subscriptions WHERE disabled_by_limit = true) as disabled_subs,
            (SELECT COUNT(*) FROM payments WHERE status = 'completed') as completed_payments,
            (SELECT SUM(amount) FROM payments WHERE status = 'completed') as total_revenue
    """)).first()
    
    print("\n" + "=" * 60)
    print("СТАТИСТИКА")
    print("=" * 60)
    print(f"Всего пользователей:        {stats[0]}")
    print(f"Активных подписок:          {stats[1]}")
    print(f"Истекших подписок:          {stats[2]}")
    print(f"Отключенных по лимиту:      {stats[3]}")
    print(f"Завершенных платежей:       {stats[4]}")
    print(f"Общая выручка:              {stats[5] or 0:.2f} ₽")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Просмотр данных из БД")
    parser.add_argument("--users", action="store_true", help="Показать пользователей")
    parser.add_argument("--payments", action="store_true", help="Показать платежи")
    parser.add_argument("--servers", action="store_true", help="Показать серверы")
    parser.add_argument("--stats", action="store_true", help="Показать статистику")
    parser.add_argument("--subscription-id", type=int, help="Показать конкретную подписку по ID")
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        if args.users:
            print_users(db)
        elif args.payments:
            print_payments(db)
        elif args.servers:
            print_servers(db)
        elif args.stats:
            print_stats(db)
        elif args.subscription_id:
            print_subscriptions(db, args.subscription_id)
        else:
            # По умолчанию показываем подписки
            print_subscriptions(db)
            print("\n")
            print_stats(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
