"""Связка оплаты (Mini App / ЮKassa) с control plane: cp_users.account_subscription_until."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.cp_user import CpUser
from db.models.device import Device

logger = logging.getLogger(__name__)

DAYS_PER_MONTH = 30


def extend_cp_subscription_for_telegram(
    db: Session,
    telegram_id: int,
    tariff_months: int,
) -> None:
    """
    Продлевает оплаченный доступ для Flutter-клиента.
    Пользователь должен был вызвать POST /attach-telegram с этим telegram_id — тогда cp_user существует.
    Если записи ещё нет (оплатил до attach) — создаём cp_user только с telegram_id.
    """
    now = datetime.now(timezone.utc)
    delta = timedelta(days=tariff_months * DAYS_PER_MONTH)

    cp = db.scalar(select(CpUser).where(CpUser.telegram_id == telegram_id))
    if not cp:
        cp = CpUser(telegram_id=telegram_id)
        db.add(cp)
        db.flush()

    acc = cp.account_subscription_until
    if acc is not None:
        if acc.tzinfo is None:
            acc = acc.replace(tzinfo=timezone.utc)
        if acc > now:
            cp.account_subscription_until = acc + delta
        else:
            cp.account_subscription_until = now + delta
    else:
        cp.account_subscription_until = now + delta

    db.add(cp)
    logger.info(
        "CP subscription extended: telegram_id=%s tariff_months=%s until=%s",
        telegram_id,
        tariff_months,
        cp.account_subscription_until,
    )


def sync_cp_after_payment_success(telegram_id: int, tariff_months: int) -> None:
    """Отдельная сессия, чтобы сбой CP не откатывал уже зафиксированную подписку Mini App."""
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        extend_cp_subscription_for_telegram(db, telegram_id, tariff_months)
        db.commit()
    except Exception:
        logger.exception("sync_cp_after_payment_success failed telegram_id=%s", telegram_id)
        db.rollback()
    finally:
        db.close()


def effective_subscription_until(device: Device) -> datetime:
    """Максимум из trial на устройстве и оплаты на аккаунте (cp_users)."""
    ends: list[datetime] = []
    d = device.subscription_until
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    ends.append(d)
    user = device.user
    if user and user.account_subscription_until:
        a = user.account_subscription_until
        if a.tzinfo is None:
            a = a.replace(tzinfo=timezone.utc)
        ends.append(a)
    return max(ends)
