"""Платежи ЮKassa (Итерация 5) + Xray доступ (Итерация 6.1)."""
import logging
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import get_or_create_user, verify_init_data
from api.server import get_least_loaded_server
from api.xray_grpc import add_user_to_xray
from bot.config import PAYMENT_RETURN_URL, YOOKASSA_SECRET_KEY, YOOKASSA_SHOP_ID
from db.models import Payment, Server, Subscription, User
from db.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["payments"])

TARIFFS = {
    "1m": (1, 100),       # 1 ключ · 1 устройство
    "3m": (3, 250),
    "family5": (1, 500),  # до 5 устройств, 1 мес
}  # tariff_id -> (months, amount_rub)


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    x_telegram_init_data: str | None = Header(None, alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
) -> User:
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="initData отсутствует")
    data = verify_init_data(x_telegram_init_data)
    if not data:
        raise HTTPException(status_code=401, detail="Неверный initData")
    user_data = data.get("user")
    if not user_data:
        raise HTTPException(status_code=401, detail="Нет данных пользователя")
    telegram_id = user_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Нет telegram_id")
    return get_or_create_user(
        db,
        telegram_id=int(telegram_id),
        username=user_data.get("username"),
        first_name=user_data.get("first_name"),
    )


class CreatePaymentRequest(BaseModel):
    tariff: str  # "1m" | "3m" | "family5"
    method: str  # "sbp" | "card"


class CreatePaymentResponse(BaseModel):
    confirmation_url: str
    payment_id: int


@router.post("/create", response_model=CreatePaymentResponse)
def create_payment(
    body: CreatePaymentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Создать платёж в ЮKassa, сохранить pending, вернуть confirmation_url."""
    if body.tariff not in TARIFFS or body.method not in ("sbp", "card"):
        raise HTTPException(status_code=400, detail="Неверный tariff или method")
    months, amount_rub = TARIFFS[body.tariff]
    amount_str = f"{amount_rub:.2f}"

    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="ЮKassa не настроена. Задайте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY в .env",
        )

    try:
        from yookassa import Configuration, Payment as YooPayment

        Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
    except ImportError:
        raise HTTPException(status_code=503, detail="yookassa не установлен: pip install yookassa")

    if not PAYMENT_RETURN_URL:
        raise HTTPException(
            status_code=503,
            detail="Не задан PAYMENT_RETURN_URL в .env",
        )

    def _payload(with_method: bool) -> dict:
        p = {
            "amount": {"value": amount_str, "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": PAYMENT_RETURN_URL},
            "capture": True,
            "description": f"KrotVPN {months} мес.",
        }
        if with_method:
            payment_method_type = "sbp" if body.method == "sbp" else "bank_card"
            p["payment_method_data"] = {"type": payment_method_type}
        return p

    def _err_msg(e: Exception) -> str:
        err_msg = "Ошибка создания платежа в ЮKassa"
        if hasattr(e, "response_body") and e.response_body:
            try:
                import json as _json
                err_body = _json.loads(e.response_body) if isinstance(e.response_body, str) else e.response_body
                desc = err_body.get("description") or err_body.get("message") or str(err_body.get("code", ""))
                if desc:
                    err_msg = str(desc)
            except Exception:
                pass
        elif getattr(e, "args", None):
            err_msg = str(e.args[0])[:500]
        return err_msg

    yoo = None
    last_error = None
    for with_method in (True, False):
        try:
            yoo = YooPayment.create(_payload(with_method))
            break
        except Exception as e:
            last_error = e
            logger.warning("YooKassa create (with_method=%s) failed: %s", with_method, e)
            if not with_method:
                raise HTTPException(status_code=502, detail=_err_msg(e)) from e
    if yoo is None and last_error is not None:
        logger.exception("YooKassa create failed: %s", last_error)
        raise HTTPException(status_code=502, detail=_err_msg(last_error)) from last_error

    yoo_id = yoo.id
    confirmation_url = ""
    if hasattr(yoo, "confirmation") and yoo.confirmation:
        c = yoo.confirmation
        confirmation_url = getattr(c, "confirmation_url", None)
        if not confirmation_url and isinstance(getattr(c, "__dict__", None), dict):
            confirmation_url = c.get("confirmation_url", "")
        if not confirmation_url and hasattr(c, "get"):
            confirmation_url = c.get("confirmation_url", "")
    if not confirmation_url:
        logger.warning("YooKassa response: id=%s confirmation=%s", yoo_id, getattr(yoo, "confirmation", None))
        raise HTTPException(status_code=502, detail="ЮKassa не вернула ссылку на оплату")

    payment = Payment(
        user_id=user.id,
        amount=float(amount_str),
        currency="RUB",
        status="pending",
        tariff_months=months,
        payment_method=body.method,
        external_id=yoo_id,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    logger.info("Payment created id=%s user_id=%s yoo_id=%s", payment.id, user.id, yoo_id)
    return CreatePaymentResponse(confirmation_url=confirmation_url, payment_id=payment.id)


@router.post("/webhook")
def webhook(request: dict, db: Session = Depends(get_db)):
    """
    Webhook от ЮKassa. В личном кабинете ЮKassa укажи URL: https://your-domain/api/payments/webhook
    Событие payment.succeeded: обновить payment → completed, создать/продлить subscription (expires_at).
    """
    event = request.get("event") or request.get("type")
    obj = request.get("object") or request
    if not obj:
        return {"ok": True}

    payment_id_yoo = obj.get("id") or obj.get("payment_id")
    status = obj.get("status")
    if not payment_id_yoo:
        return {"ok": True}

    if event == "payment.succeeded" or status == "succeeded":
        payment_row = db.execute(
            select(Payment)
            .where(Payment.external_id == str(payment_id_yoo))
            .where(Payment.status == "pending")
        )
        payment = payment_row.scalars().first()
        if not payment:
            logger.warning("Webhook: payment not found or already processed, yoo_id=%s", payment_id_yoo)
            return {"ok": True}

        payment.status = "completed"
        db.commit()

        now = datetime.now(timezone.utc)
        days_per_month = 30  # 1 мес = 30 дней, 3 мес = 90 дней
        expires_at = now + timedelta(days=payment.tariff_months * days_per_month)

        existing = db.execute(
            select(Subscription)
            .where(Subscription.user_id == payment.user_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        ).scalars().first()

        if existing and existing.expires_at and existing.expires_at.replace(tzinfo=timezone.utc) > now:
            # Активная подписка — только продлить срок, Xray не трогаем
            base = existing.expires_at.replace(tzinfo=timezone.utc) if existing.expires_at.tzinfo is None else existing.expires_at
            expires_at = base + timedelta(days=payment.tariff_months * days_per_month)
            existing.expires_at = expires_at
            existing.status = "active"
            db.commit()
            logger.info("Subscription extended user_id=%s expires_at=%s", payment.user_id, expires_at)
        elif existing and existing.uuid and existing.server_id:
            # Просроченная подписка с UUID — вернуть того же пользователя в Xray (enable), продлить срок
            server_row = db.execute(select(Server).where(Server.id == existing.server_id)).scalars().first()
            if server_row:
                email = f"user_{payment.user_id}"
                try:
                    add_user_to_xray(
                        host=server_row.host,
                        grpc_port=server_row.grpc_port,
                        user_uuid=existing.uuid,
                        email=email,
                    )
                    server_row.active_users += 1
                    db.add(server_row)
                    existing.expires_at = now + timedelta(days=payment.tariff_months * days_per_month)
                    existing.status = "active"
                    db.add(existing)
                    db.commit()
                    logger.info(
                        "Subscription renewed (same UUID) user_id=%s uuid=%s expires_at=%s",
                        payment.user_id, existing.uuid, existing.expires_at,
                    )
                except Exception as e:
                    logger.exception("Xray AddUser (renew) failed: %s", e)
                    db.rollback()
            else:
                # Сервер удалён — создаём новую подписку как для нового пользователя
                existing = None
        else:
            existing = None

        if existing is None:
            # Новый пользователь или нет uuid/server_id — создать новую подписку и AddUser
            server = get_least_loaded_server(db)
            sub_uuid: str | None = None
            sub_server_id: int | None = None
            if server:
                sub_uuid = str(uuid4())
                email = f"user_{payment.user_id}"
                try:
                    add_user_to_xray(
                        host=server.host,
                        grpc_port=server.grpc_port,
                        user_uuid=sub_uuid,
                        email=email,
                    )
                    sub_server_id = server.id
                    server.active_users += 1
                    db.add(server)
                    logger.info(
                        "Xray AddUser ok: user_id=%s server_id=%s uuid=%s",
                        payment.user_id, server.id, sub_uuid,
                    )
                except Exception as e:
                    logger.exception("Xray AddUser failed, subscription without key: %s", e)
                    sub_uuid = None
                    sub_server_id = None
            else:
                logger.warning("No enabled server for user_id=%s, subscription without key", payment.user_id)

            sub = Subscription(
                user_id=payment.user_id,
                status="active",
                expires_at=expires_at,
                tariff_months=payment.tariff_months,
                uuid=sub_uuid,
                server_id=sub_server_id,
            )
            db.add(sub)
            db.commit()
            logger.info("Subscription created user_id=%s expires_at=%s server_id=%s", payment.user_id, expires_at, sub_server_id)

    return {"ok": True}
