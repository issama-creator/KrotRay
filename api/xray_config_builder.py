"""Сборка JSON конфигурации для клиента (цепочка bridge → NL)."""
from __future__ import annotations

import uuid
from typing import Any

from db.models.cp_server import CpServer
from db.models.device import Device


def build_client_config(bridge: CpServer, nl: CpServer, device: Device) -> dict[str, Any]:
    """
    Возвращает структуру, пригодную для клиента / flutter_vless.
    Включает стандартные поля Xray Reality + цепочку из двух узлов.
    """
    client_uuid = str(uuid.uuid4())
    return {
        "version": 1,
        "device_id": device.device_id,
        "plan_type": device.plan_type,
        "chain": ["bridge", "nl"],
        "outbounds": [
            _vless_outbound("bridge-hop", bridge, client_uuid),
            _vless_outbound("nl-hop", nl, client_uuid),
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {"type": "field", "inboundTag": ["bridge-hop"], "outboundTag": "nl-hop"},
            ],
        },
        "meta": {
            "bridge": {"id": bridge.id, "role": bridge.role, "ip": bridge.ip},
            "nl": {"id": nl.id, "role": nl.role, "ip": nl.ip},
        },
    }


def _vless_outbound(tag: str, node: CpServer, user_id: str) -> dict[str, Any]:
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": node.ip,
                    "port": 443,
                    "users": [
                        {
                            "id": user_id,
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
                "serverName": node.sni,
                "fingerprint": "chrome",
                "publicKey": node.public_key,
                "shortId": node.short_id,
                "spiderX": node.path or "/",
            },
        },
    }
