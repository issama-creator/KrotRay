"""Фоновая задача: отключение просроченных подписок (Итерация 6.2)."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.xray_grpc import remove_user_from_xray
from bot.config import XRAY_INBOUND_TAG
from db.models import Server, Subscription
from db.session import SessionLocal

logger = logging.getLogger(__name__)


def run_expired_subscriptions() -> None:
    """
    Находит подписки с status=active и expires_at < now(),
    удаляет пользователя из Xray (RemoveUser), ставит status=expired, уменьшает server.active_users.
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
                email = f"user_{sub.user_id}"
                if sub.server_id and sub.uuid:
                    server_row = db.execute(select(Server).where(Server.id == sub.server_id))
                    server = server_row.scalars().first()
                    if server:
                        remove_user_from_xray(
                            host=server.host,
                            grpc_port=server.grpc_port,
                            email=email,
                            inbound_tag=XRAY_INBOUND_TAG,
                        )
                        server.active_users = max(0, server.active_users - 1)
                        db.add(server)
                sub.status = "expired"
                db.add(sub)
                db.commit()
                logger.info("Expired job: user_id=%s subscription_id=%s disabled", sub.user_id, sub.id)
            except Exception as e:
                logger.exception("Expired job: failed user_id=%s sub_id=%s: %s", sub.user_id, sub.id, e)
                db.rollback()
    finally:
        db.close()
