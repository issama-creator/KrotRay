"""Dynamic cloaking config API and payment landing page."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from bot.config import CLOAK_TELEGRAM_DEEP_LINK_BASE, CLOAK_WHITE_PAGE_URL
from services.minimal_lb import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cloaking"])

_IP_API_URL = "http://ip-api.com/json/{ip}?fields=status,countryCode,message"
_FULL_MODE_COUNTRY = "RU"
_FULL_MODE_AFTER_VISITS = 3
_CLOAK_VISITS_KEY_PREFIX = "cloak:visits:"
_CLOAK_MODE_STATE_KEY_PREFIX = "cloak:mode_state:"
_CLOAK_GEO_CACHE_KEY_PREFIX = "cloak:geo:"
_MODE_CONFIRM_CHECKS = 4
_MODE_REVALIDATE_SEC = 60 * 60 * 24 * 7
_GEO_CACHE_TTL_SEC = 60 * 60 * 24

_TARIFFS: list[dict[str, Any]] = [
    {"id": "monthly", "name": "1 Month", "price": "299 RUB"},
    {"id": "quarterly", "name": "3 Months", "price": "799 RUB"},
    {"id": "semiannual", "name": "6 Months", "price": "1399 RUB"},
]

_WHITE_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VLESS and XTLS Reality Notes</title>
  <style>
    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: #ffffff;
      color: #0f172a;
      line-height: 1.62;
    }
    main {
      max-width: 900px;
      margin: 40px auto;
      padding: 0 20px 40px;
    }
    h1 {
      font-size: 28px;
      margin-bottom: 16px;
    }
    p {
      margin: 0 0 14px;
    }
  </style>
</head>
<body>
  <main>
    <h1>Technical White Page: VLESS and XTLS Reality</h1>
    <p>
      VLESS is a lightweight transport protocol used in modern proxy stacks where authentication and
      stream control are separated from payload encryption details. In practical deployments, VLESS
      is frequently combined with transport layers such as TCP, gRPC, WebSocket, or HTTP/2 depending
      on network constraints and the desired traffic profile. Engineers often choose VLESS because its
      framing overhead is small, implementation patterns are well documented in the ecosystem, and it
      allows flexible routing rules that map users to dedicated outbound chains. In comparison with
      legacy approaches, VLESS-based stacks can simplify key rotation procedures and reduce accidental
      coupling between account lifecycle logic and packet processing logic.
    </p>
    <p>
      XTLS Reality is typically discussed as a camouflage-oriented handshake layer. It aims to make
      observable characteristics look similar to ordinary encrypted web sessions while preserving
      operator-level control over inbound validation. Instead of exposing an obvious static certificate
      pattern tied to a single endpoint identity, Reality relies on controlled cryptographic settings,
      short identifiers, and server-side policy validation. This architecture can help reduce simple
      fingerprint-based blocking methods that target repetitive handshake signatures. It does not claim
      to guarantee invisibility, but it can increase resilience in unstable networks where active and
      passive traffic classification is common.
    </p>
    <p>
      From an operational perspective, production systems should include health checks, assignment
      balancing, and adaptive failover. A robust control plane keeps a catalog of available edge nodes,
      tracks heartbeat freshness, and removes stale nodes from rotation before client quality degrades.
      Client assignment logic can be deterministic for cache efficiency or weighted for fairness, but
      both strategies require consistent identity keys and strict timeout boundaries. Storage layering
      also matters: many teams keep durable metadata in SQL and maintain low-latency runtime state in
      an in-memory data store. This split reduces contention for read-heavy paths while preserving audit
      visibility for account and lifecycle operations.
    </p>
    <p>
      Security hygiene for VLESS and Reality deployments should include strict separation of concerns.
      Authentication secrets, transport keys, and administrative credentials must not share the same
      rotation schedule or exposure surface. Logging policies should avoid storing full user identifiers
      in plaintext wherever possible; structured redaction and short retention windows can reduce risk.
      API gateways should normalize headers and enforce sane request rates to prevent amplification
      attempts. On client platforms, stable device identifiers are useful for anti-abuse logic, but they
      should be generated and persisted with care, avoiding accidental reset on every application launch.
      When used responsibly, these practices improve reliability and observability without changing core
      protocol semantics.
    </p>
    <p>
      Performance tuning usually starts with transport selection and congestion behavior. Networks with
      aggressive middleboxes may favor one encapsulation style over another, and mobile conditions can
      vary significantly between regions and carriers. Teams often profile connection setup latency,
      packet loss tolerance, and reconnection intervals before finalizing defaults. Long-term maintainable
      deployments invest in metrics pipelines for assignment drift, server saturation, and handshake
      failures by cohort. This gives operators an evidence-based way to adjust routing and infrastructure
      capacity while keeping service behavior predictable under changing demand.
    </p>
  </main>
</body>
</html>
"""


def _extract_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip
    return request.client.host if request.client else ""


def _geo_country_code(ip: str) -> str:
    if not ip:
        return ""
    if ip.startswith("127.") or ip == "::1":
        return _FULL_MODE_COUNTRY
    try:
        resp = requests.get(_IP_API_URL.format(ip=ip), timeout=2.5)
        data = resp.json() if resp.ok else {}
    except Exception as exc:
        logger.warning("cloaking geo lookup failed ip=%s err=%s", ip, exc)
        return ""
    if data.get("status") != "success":
        logger.warning("cloaking geo lookup unsuccessful ip=%s message=%s", ip, data.get("message"))
        return ""
    return str(data.get("countryCode") or "").upper()


def _geo_country_code_cached(ip: str) -> str:
    if not ip:
        return ""
    key = f"{_CLOAK_GEO_CACHE_KEY_PREFIX}{ip}"
    try:
        client = get_redis()
        cached = client.get(key)
        if cached:
            return str(cached).upper()
        value = _geo_country_code(ip)
        if value:
            client.setex(key, _GEO_CACHE_TTL_SEC, value)
        return value
    except Exception as exc:
        logger.warning("cloaking geo cache fallback ip=%s err=%s", ip, exc)
        return _geo_country_code(ip)


def _is_full_mode(*, country_code: str, lang: str, sid: str) -> bool:
    lang_is_ru = lang.lower() == "ru"
    is_real_device = sid == "0"
    # VPN fallback: for ru language on a real device, allow full mode
    # even when IP geolocation is not RU.
    return (country_code == _FULL_MODE_COUNTRY and lang_is_ru and is_real_device) or (lang_is_ru and is_real_device)


def _visit_key(uid: str) -> str:
    return f"{_CLOAK_VISITS_KEY_PREFIX}{uid}"


def _state_key(identity: str) -> str:
    return f"{_CLOAK_MODE_STATE_KEY_PREFIX}{identity}"


def _get_mode_state(identity: str) -> dict[str, Any]:
    key = _state_key(identity)
    try:
        client = get_redis()
        raw = client.get(key)
        if not raw:
            return {"mode": "", "checks_count": 0, "confirmed": False, "last_check_ts": 0}
        parsed = json.loads(str(raw))
        return {
            "mode": str(parsed.get("mode") or ""),
            "checks_count": int(parsed.get("checks_count") or 0),
            "confirmed": bool(parsed.get("confirmed") or False),
            "last_check_ts": int(parsed.get("last_check_ts") or 0),
        }
    except Exception as exc:
        logger.warning("cloaking mode state read failed identity=%s err=%s", identity, exc)
        return {"mode": "", "checks_count": 0, "confirmed": False, "last_check_ts": 0}


def _save_mode_state(identity: str, state: dict[str, Any]) -> None:
    key = _state_key(identity)
    try:
        client = get_redis()
        client.setex(key, 60 * 60 * 24 * 90, json.dumps(state))
    except Exception as exc:
        logger.warning("cloaking mode state write failed identity=%s err=%s", identity, exc)


def _increment_visit_count(uid: str) -> int:
    key = _visit_key(uid)
    try:
        client = get_redis()
        visits = int(client.incr(key))
        if visits == 1:
            client.expire(key, 60 * 60 * 24 * 90)
        return visits
    except Exception as exc:
        logger.warning("cloaking visit counter increment failed uid=%s err=%s", uid, exc)
        return 1


def _get_visit_count(uid: str) -> int:
    key = _visit_key(uid)
    try:
        client = get_redis()
        raw = client.get(key)
        if raw is None:
            return 0
        return int(raw)
    except Exception as exc:
        logger.warning("cloaking visit counter read failed uid=%s err=%s", uid, exc)
        return 0


def _build_config_payload(*, mode: str, uid: str, lang: str, sid: str, request: Request, checks_count: int, confirmed: bool) -> dict[str, Any]:
    if mode == "full":
        pay_url = f"{request.base_url}api/pay?uid={uid}&lang={lang}&sid={sid}".replace(" ", "")
        return {
            "mode": "full",
            "ui": {
                "show_trial": True,
                "show_upgrade": True,
                "show_webview": True,
            },
            "texts": {
                "banner_title": "Ostalsya 1 den",
                "banner_subtitle": "Dlya prodolzheniya potrebuyetsya konfiguratsiya",
                "button_text": "Prodolzhit podklyuchenie",
            },
            "links": {
                "management_url": pay_url,
                "telegram_bot": CLOAK_TELEGRAM_DEEP_LINK_BASE,
            },
            "tariffs": _TARIFFS,
            "mode_meta": {
                "checks_count": checks_count,
                "confirmed": confirmed,
                "revalidate_after_sec": _MODE_REVALIDATE_SEC,
            },
        }
    return {
        "mode": "safe",
        "ui": {
            "show_trial": False,
            "show_upgrade": False,
            "show_webview": False,
        },
        "texts": {
            "empty_title": "Dobavte konfiguratsiyu",
            "empty_subtitle": "Importiruyte konfiguratsiyu dlya podklyucheniya",
            "technical_note": (
                "Technical Guide: this build currently exposes protocol documentation only. "
                f"Detailed notes are available at {CLOAK_WHITE_PAGE_URL}."
            ),
        },
        "links": {},
        "mode_meta": {
            "checks_count": checks_count,
            "confirmed": confirmed,
            "revalidate_after_sec": _MODE_REVALIDATE_SEC,
        },
    }


@router.get("/api/config")
def get_dynamic_config(
    request: Request,
    uid: str = Query(..., min_length=1, max_length=128),
    lang: str = Query(..., min_length=2, max_length=8),
    sid: str = Query(..., pattern="^[01]$"),
    device_id: str | None = Query(default=None, max_length=128),
    timezone: str | None = Query(default=None, max_length=64),
    languages: str | None = Query(default=None, max_length=256),
):
    visits = _increment_visit_count(uid)
    identity = (device_id or uid).strip()
    state = _get_mode_state(identity)
    now_ts = int(time.time())
    fresh_confirmed = bool(state["confirmed"]) and (now_ts - int(state["last_check_ts"])) < _MODE_REVALIDATE_SEC

    if fresh_confirmed:
        detected_mode = str(state["mode"] or "safe")
    else:
        ip = _extract_client_ip(request)
        country_code = _geo_country_code_cached(ip)
        detected_mode = "full" if _is_full_mode(country_code=country_code, lang=lang, sid=sid) else "safe"

    if detected_mode == str(state["mode"]):
        checks_count = int(state["checks_count"]) + 1
    else:
        checks_count = 1
    confirmed = checks_count >= _MODE_CONFIRM_CHECKS
    _save_mode_state(
        identity,
        {
            "mode": detected_mode,
            "checks_count": checks_count,
            "confirmed": confirmed,
            "last_check_ts": now_ts,
            "timezone": timezone or "",
            "languages": languages or "",
        },
    )

    effective_mode = "safe" if visits <= _FULL_MODE_AFTER_VISITS else detected_mode
    payload = _build_config_payload(
        mode=effective_mode,
        uid=uid,
        lang=lang,
        sid=sid,
        request=request,
        checks_count=checks_count,
        confirmed=confirmed,
    )
    payload["mode_meta"]["visits_left_to_full"] = max(0, _FULL_MODE_AFTER_VISITS - visits + 1)
    payload["mode_meta"]["source"] = "cache" if fresh_confirmed else "detector"
    return payload


@router.get("/api/pay", response_class=HTMLResponse)
def get_pay_page(request: Request, uid: str = Query(..., min_length=1, max_length=128)):
    visits = _get_visit_count(uid)
    if visits <= _FULL_MODE_AFTER_VISITS:
        return HTMLResponse(content=_WHITE_PAGE_HTML)
    ip = _extract_client_ip(request)
    country_code = _geo_country_code(ip)
    # Keep pay page behavior aligned with /api/config VPN fallback.
    lang = (request.query_params.get("lang") or "").strip().lower()
    sid = (request.query_params.get("sid") or "").strip()
    allow_vpn_fallback = bool(lang and sid)
    allow_redirect = country_code == _FULL_MODE_COUNTRY or (
        allow_vpn_fallback and _is_full_mode(country_code=country_code, lang=lang, sid=sid)
    )
    if allow_redirect:
        deep_link = f"{CLOAK_TELEGRAM_DEEP_LINK_BASE}{uid}"
        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Redirecting</title>
</head>
<body>
  <p>Redirecting...</p>
  <script>
    setTimeout(function() {{
      window.location.href = {deep_link!r};
    }}, 500);
  </script>
</body>
</html>"""
        return HTMLResponse(content=html)
    return HTMLResponse(content=_WHITE_PAGE_HTML)

