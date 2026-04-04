"""Control plane REST API: регистрация устройства, привязка Telegram, выдача конфигурации."""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import Float, cast, func, nulls_last, select
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
# Чуть больше интервала пинга Flutter (3–4 мин), чтобы не мигать «офлайн» из-за джиттера сети.
TUNNEL_ACTIVE_GRACE = timedelta(minutes=5)

# Балансировка cp_servers (схема devices и JSON ответа /config не меняются).
# max_users — технический максимум; реальную «заполненность» держим примерно 70–80% от него.
# Отдаём узлы только пока (current_users/max_users) < 0.8 — запас, если current_users неточный.
_CP_LOAD_CAP = 0.8
_CP_TOP_K = 3


def _load_percent(current_users: int, max_users: int) -> float:
    if max_users <= 0:
        return 0.0
    return round(100.0 * float(current_users) / float(max_users), 2)


def _cp_no_servers_503() -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": "no available servers"})


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


class VpnHeartbeatBody(BaseModel):
    """Пинг с клиента: пока VPN включён — раз в 3–4 мин; connected=false при явном отключении."""

    device_id: str = Field(..., min_length=1)
    connected: bool = True


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
    existing = db.scalar(
        select(Device).options(joinedload(Device.user)).where(Device.device_id == did_s),
    )
    if existing:
        eff = effective_subscription_until(existing)
        return RegisterResponse(subscription_until=eff.isoformat())
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


def _pick_server(db: Session, role: str) -> CpServer | None:
    """
    Фильтр: active, current_users < max_users, load < _CP_LOAD_CAP (80%).
    ORDER BY load ASC, latency; LIMIT 3; случайный из трёх — anti-spike.
    """
    raw_load = cast(CpServer.current_users, Float) / cast(CpServer.max_users, Float)
    q = (
        select(CpServer)
        .where(CpServer.role == role)
        .where(CpServer.active.is_(True))
        .where(CpServer.max_users > 0)
        .where(CpServer.current_users < CpServer.max_users)
        .where(raw_load < _CP_LOAD_CAP)
        .order_by(raw_load.asc(), nulls_last(CpServer.latency.asc()))
        .limit(_CP_TOP_K)
    )
    rows = list(db.scalars(q).all())
    if not rows:
        return None
    return random.choice(rows)


def _ensure_test_servers_if_empty(db: Session) -> None:
    total = db.scalar(select(func.count()).select_from(CpServer)) or 0
    if total > 0:
        return
    db.add_all(
        [
            CpServer(
                ip="fake-nl",
                role=ROLE_NL,
                group_id="g1",
                public_key="fake_key",
                short_id="abcd",
                sni="fake.nl",
                path="/",
                max_users=100,
                current_users=0,
                active=True,
            ),
            CpServer(
                ip="fake-bridge",
                role=ROLE_STANDARD,
                group_id="g1",
                public_key="fake_key",
                short_id="abcd",
                sni="fake.bridge",
                path="/",
                max_users=500,
                current_users=0,
                active=True,
            ),
        ]
    )
    db.commit()
    logger.info("Seeded test cp_servers: fake-nl + fake-bridge")


def _build_test_config(nl: CpServer) -> dict:
    return {
        "log": {"loglevel": "warning"},
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": nl.ip,
                            "port": 443,
                            "users": [
                                {
                                    "id": "11111111-1111-1111-1111-111111111111",
                                    "encryption": "none",
                                    "flow": "xtls-rprx-vision",
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "publicKey": nl.public_key,
                        "shortId": nl.short_id,
                    },
                },
            }
        ],
    }


@router.get("/config")
def get_config(
    device_id: Annotated[str | None, Query(description="UUID устройства")] = None,
    db: Session = Depends(get_db),
) -> dict:
    # Быстрый тестовый режим: /config без параметров возвращает конфиг без проверки подписки.
    if not device_id:
        _ensure_test_servers_if_empty(db)
        nl = _pick_server(db, ROLE_NL)
        if not nl:
            return _cp_no_servers_503()
        logger.info(
            "cp_pick test: role=nl server_id=%s current_users=%s max_users=%s load_percent=%s",
            nl.id,
            nl.current_users,
            nl.max_users,
            _load_percent(nl.current_users, nl.max_users),
        )
        nl.current_users += 1
        db.commit()
        return _build_test_config(nl)

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
            return _cp_no_servers_503()
        logger.info(
            "cp_pick: role=%s server_id=%s current_users=%s max_users=%s load_percent=%s",
            bridge_role,
            bridge.id,
            bridge.current_users,
            bridge.max_users,
            _load_percent(bridge.current_users, bridge.max_users),
        )
        logger.info(
            "cp_pick: role=nl server_id=%s current_users=%s max_users=%s load_percent=%s",
            nl.id,
            nl.current_users,
            nl.max_users,
            _load_percent(nl.current_users, nl.max_users),
        )
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


@router.post("/vpn-heartbeat")
def vpn_heartbeat(body: VpnHeartbeatBody, db: Session = Depends(get_db)) -> dict:
    """Flutter: при активном туннеле вызывать каждые 3–4 мин; connected=false — сброс метки в БД."""
    did_s = str(_parse_uuid(body.device_id))
    device = db.scalar(
        select(Device).options(joinedload(Device.user)).where(Device.device_id == did_s),
    )
    if not device:
        raise HTTPException(status_code=404, detail="device not found")
    now = datetime.now(timezone.utc)
    if effective_subscription_until(device) < now:
        raise HTTPException(status_code=403, detail="subscription expired")
    if body.connected:
        device.tunnel_last_seen_at = now
    else:
        device.tunnel_last_seen_at = None
    db.commit()
    return {
        "ok": True,
        "tunnel_last_seen_at": device.tunnel_last_seen_at.isoformat()
        if device.tunnel_last_seen_at
        else None,
    }


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
    seen = device.tunnel_last_seen_at
    tunnel_likely_active = bool(
        seen is not None and (now - seen) <= TUNNEL_ACTIVE_GRACE
    )
    return {
        "subscription_until": eff.isoformat(),
        "days_left": days_left,
        "has_access": eff >= now,
        "tunnel_last_seen_at": seen.isoformat() if seen else None,
        "tunnel_likely_active": tunnel_likely_active,
    }
