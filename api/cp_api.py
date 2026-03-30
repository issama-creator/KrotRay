"""Control plane REST API: регистрация устройства, привязка Telegram, выдача конфигурации."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, nulls_last, select
from sqlalchemy.orm import Session, joinedload

from api.cp_subscription_sync import effective_subscription_until
from api.xray_config_builder import build_client_config
from db.models.cp_server import CpServer
from db.models.cp_user import CpUser
from db.models.device import Device
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["control-plane"])

TRIAL_DAYS = 7
ROLE_NL = "nl"
ROLE_STANDARD = "standard_bridge"
ROLE_BYPASS = "bypass_bridge"
PLAN_STANDARD = "standard"
PLAN_BYPASS = "bypass"


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


class RegisterBody(BaseModel):
    device_id: str = Field(..., min_length=1)
    platform: str


class RegisterResponse(BaseModel):
    subscription_until: str


class AttachBody(BaseModel):
    device_id: str
    telegram_id: int


def _parse_uuid(s: str) -> uuid.UUID:
    try:
        return uuid.UUID(s.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid device_id") from e


@router.post("/register", response_model=RegisterResponse)
def register(body: RegisterBody, db: Session = Depends(get_db)) -> RegisterResponse:
    if body.platform not in ("android", "ios"):
        raise HTTPException(status_code=400, detail="platform must be android or ios")
    did = _parse_uuid(body.device_id)
    did_s = str(did)
    existing = db.scalar(select(Device).where(Device.device_id == did_s))
    if existing:
        return RegisterResponse(
            subscription_until=existing.subscription_until.isoformat(),
        )
    user = CpUser()
    db.add(user)
    db.flush()
    until = datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)
    dev = Device(
        device_id=did_s,
        user_id=user.id,
        platform=body.platform,
        subscription_until=until,
        plan_type=PLAN_STANDARD,
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    logger.info("CP register: new device_id=%s user_id=%s until=%s", did_s, user.id, until)
    return RegisterResponse(subscription_until=until.isoformat())


@router.post("/attach-telegram")
def attach_telegram(body: AttachBody, db: Session = Depends(get_db)) -> dict:
    did_s = str(_parse_uuid(body.device_id))
    telegram_id = body.telegram_id
    device = db.scalar(select(Device).where(Device.device_id == did_s))
    if not device:
        raise HTTPException(status_code=404, detail="device not found")

    old_owner_id = device.user_id
    tg_user = db.scalar(select(CpUser).where(CpUser.telegram_id == telegram_id))
    if not tg_user:
        tg_user = CpUser(telegram_id=telegram_id)
        db.add(tg_user)
        db.flush()

    ends: list[datetime] = [device.subscription_until]
    if tg_user.account_subscription_until:
        ends.append(tg_user.account_subscription_until)
    for other in db.scalars(
        select(Device).where(Device.user_id == tg_user.id, Device.id != device.id),
    ):
        ends.append(other.subscription_until)

    device.user_id = tg_user.id
    device.subscription_until = max(ends)

    old_owner = db.get(CpUser, old_owner_id)
    if old_owner and old_owner.id != tg_user.id:
        remaining = db.scalar(
            select(func.count()).select_from(Device).where(Device.user_id == old_owner.id),
        )
        if remaining == 0:
            db.delete(old_owner)

    db.commit()
    device_fresh = db.scalar(
        select(Device).options(joinedload(Device.user)).where(Device.device_id == did_s),
    )
    if not device_fresh:
        raise HTTPException(status_code=500, detail="device not found after attach")
    eff = effective_subscription_until(device_fresh)
    logger.info(
        "CP attach-telegram: device_id=%s telegram_id=%s effective_until=%s",
        did_s,
        telegram_id,
        eff,
    )
    return {"ok": True, "subscription_until": eff.isoformat()}


def _pick_server(
    db: Session,
    role: str,
) -> CpServer | None:
    q = (
        select(CpServer)
        .where(CpServer.role == role)
        .where(CpServer.active.is_(True))
        .where(CpServer.current_users < CpServer.max_users)
        .order_by(CpServer.current_users.asc(), nulls_last(CpServer.latency.asc()))
    )
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        q = q.with_for_update(skip_locked=True)
    return db.scalars(q).first()


@router.get("/config")
def get_config(
    device_id: Annotated[str, Query(..., description="UUID устройства")],
    db: Session = Depends(get_db),
) -> dict:
    did_s = str(_parse_uuid(device_id))
    device = db.scalar(
        select(Device).options(joinedload(Device.user)).where(Device.device_id == did_s),
    )
    if not device:
        raise HTTPException(status_code=404, detail="device not found")

    now = datetime.now(timezone.utc)
    sub_until = effective_subscription_until(device)
    if sub_until < now:
        raise HTTPException(status_code=403, detail="subscription expired")

    bridge_role = ROLE_STANDARD if device.plan_type == PLAN_STANDARD else ROLE_BYPASS
    try:
        bridge = _pick_server(db, bridge_role)
        nl = _pick_server(db, ROLE_NL)
        if not bridge or not nl:
            raise HTTPException(status_code=503, detail="no capacity")
        bridge.current_users += 1
        nl.current_users += 1
        cfg = build_client_config(bridge, nl, device)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("CP config: failed for device_id=%s", did_s)
        raise HTTPException(status_code=500, detail="config error") from None

    return cfg


@router.get("/subscription")
def subscription_status(
    device_id: Annotated[str, Query(..., description="UUID устройства")],
    db: Session = Depends(get_db),
) -> dict:
    """Для Flutter: показать дату окончания и дни без выдачи /config (после оплаты в боте)."""
    did_s = str(_parse_uuid(device_id))
    device = db.scalar(
        select(Device).options(joinedload(Device.user)).where(Device.device_id == did_s),
    )
    if not device:
        raise HTTPException(status_code=404, detail="device not found")
    now = datetime.now(timezone.utc)
    eff = effective_subscription_until(device)
    delta = eff - now
    days_left = max(0, delta.days)
    return {
        "subscription_until": eff.isoformat(),
        "days_left": days_left,
        "has_access": eff >= now,
    }
