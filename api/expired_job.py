"""Фоновая задача: отключение просроченных подписок (Итерация 6.2)."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from db.models import Subscription
from db.session import SessionLocal

logger = logging.getLogger(__name__)


def run_expired_subscriptions() -> None:
    """
    Находит подписки с status=active и expires_at < now(),
    ставит status=expired. UUID в Xray не трогаем — пользователь остаётся в Xray,
    при продлении переиспользуем тот же ключ.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rows = db.execute(
            select(Subscription)
            .where(Subscription.status == "active")
            .where(Subscription.expires_at < now)
        )
        subs = list(rows.scalars().all())
        if not subs:
            return
        logger.info("Expired job: found %s subscriptions to disable", len(subs))
        for sub in subs:
            try:
                sub.status = "expired"
                db.add(sub)
                db.commit()
                logger.info("Expired job: user_id=%s subscription_id=%s disabled (UUID left in Xray)", sub.user_id, sub.id)
            except Exception as e:
                logger.exception("Expired job: failed user_id=%s sub_id=%s: %s", sub.user_id, sub.id, e)
                db.rollback()
    finally:
        db.close()
