"""Worker для проверки лимита устройств через Xray Stats API.

Проверяет каждые 60 секунд активные подписки и отключает/включает пользователей
в зависимости от количества активных соединений.
"""
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.session import SessionLocal
from db.models import Server, Subscription
from services.xray_client import get_connections, disable_user, enable_user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # секунды


def check_subscription(subscription: Subscription, db: Session) -> None:
    """
    Проверить одну подписку и применить ограничения при необходимости.
    
    :param subscription: объект подписки из БД
    :param db: сессия БД
    """
    if not subscription.uuid or not subscription.server_id:
        logger.debug("Subscription %d: нет uuid или server_id, пропускаем", subscription.id)
        return
    
    server = db.execute(select(Server).where(Server.id == subscription.server_id)).scalar_one_or_none()
    if not server:
        logger.warning("Subscription %d: server_id=%d не найден", subscription.id, subscription.server_id)
        return
    
    email = f"user_{subscription.user_id}"
    
    try:
        # Получить количество активных соединений через Stats API
        connections = get_connections(server.host, server.grpc_port, subscription.uuid)
        logger.debug(
            "Subscription %d: uuid=%s connections=%d allowed=%d",
            subscription.id, subscription.uuid, connections, subscription.allowed_devices
        )
        
        # Проверка превышения лимита
        if connections > subscription.allowed_devices:
            # Увеличиваем счетчик нарушений
            subscription.violation_count += 1
            logger.warning(
                "Subscription %d: превышение лимита! connections=%d > allowed=%d violation_count=%d",
                subscription.id, connections, subscription.allowed_devices, subscription.violation_count
            )
            
            # Если нарушений >= 2, отключаем пользователя
            if subscription.violation_count >= 2 and not subscription.disabled_by_limit:
                try:
                    disable_user(
                        host=server.host,
                        grpc_port=server.grpc_port,
                        user_uuid=subscription.uuid,
                        email=email,
                    )
                    subscription.disabled_by_limit = True
                    # status остается "active", отключение через disabled_by_limit
                    db.commit()
                    logger.info(
                        "Subscription %d: пользователь отключен из-за превышения лимита устройств",
                        subscription.id
                    )
                except Exception as e:
                    logger.exception("Subscription %d: ошибка при отключении пользователя", subscription.id)
                    db.rollback()
            else:
                db.commit()
        else:
            # Соединений в норме
            if subscription.violation_count > 0:
                subscription.violation_count = 0
                logger.info(
                    "Subscription %d: соединения в норме, violation_count сброшен",
                    subscription.id
                )
            
            # Если пользователь был отключен из-за лимита, включаем обратно
            if subscription.disabled_by_limit:
                try:
                    enable_user(
                        host=server.host,
                        grpc_port=server.grpc_port,
                        user_uuid=subscription.uuid,
                        email=email,
                    )
                    subscription.disabled_by_limit = False
                    # status уже "active", просто сбрасываем флаг
                    db.commit()
                    logger.info(
                        "Subscription %d: пользователь автоматически включен (соединения в норме)",
                        subscription.id
                    )
                except Exception as e:
                    logger.exception("Subscription %d: ошибка при включении пользователя", subscription.id)
                    db.rollback()
            else:
                db.commit()
                
    except Exception as e:
        logger.exception("Subscription %d: ошибка при проверке", subscription.id)
        db.rollback()


def run_worker() -> None:
    """Основной цикл worker'а."""
    logger.info("Device limiter worker запущен (интервал проверки: %d сек)", CHECK_INTERVAL)
    
    while True:
        try:
            db = SessionLocal()
            try:
                now = datetime.now(timezone.utc)
                
                # Получить все активные подписки с UUID и server_id
                subscriptions = db.execute(
                    select(Subscription)
                    .where(Subscription.status == "active")
                    .where(Subscription.expires_at > now)
                    .where(Subscription.uuid.isnot(None))
                    .where(Subscription.server_id.isnot(None))
                ).scalars().all()
                
                logger.info("Проверка %d активных подписок", len(subscriptions))
                
                for subscription in subscriptions:
                    check_subscription(subscription, db)
                
            finally:
                db.close()
            
            # Ждем перед следующей проверкой
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Worker остановлен пользователем")
            break
        except Exception as e:
            logger.exception("Критическая ошибка в worker'е")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_worker()
