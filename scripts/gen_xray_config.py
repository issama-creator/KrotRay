#!/usr/bin/env python3
"""
Генерирует полный config.json для Xray из короткого файла переменных.
Не нужно править большой конфиг — только 5 полей в xray_vars.json.

Использование на новом сервере:
  1. Скопируй docs/xray_vars.example.json в xray_vars.json
  2. Поменяй private_key, short_id (для нового сервера — свои ключи Reality)
  3. python3 gen_xray_config.py < xray_vars.json > /usr/local/etc/xray/config.json
  или: python3 gen_xray_config.py xray_vars.json
"""
import json
import sys


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            vars_ = json.load(f)
    else:
        vars_ = json.load(sys.stdin)

    api_port = int(vars_.get("api_port", 8081))
    vless_port = int(vars_.get("vless_port", 443))
    private_key = vars_.get("private_key", "")
    short_id = vars_.get("short_id", "568d2499")
    first_client_uuid = vars_.get("first_client_uuid", "c8e59e9b-7d1f-424f-9440-e464b2a9fdd1")
    sni_host = vars_.get("sni_host", "www.apple.com").strip() or "www.apple.com"

    config = {
        "log": {"loglevel": "warning"},
        "api": {"tag": "api", "services": ["HandlerService"]},
        "inbounds": [
            {
                "tag": "vless-in",
                "port": vless_port,
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"id": first_client_uuid, "flow": "xtls-rprx-vision"}
                    ],
                    "decryption": "none"
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": f"{sni_host}:443",
                        "xver": 0,
                        "serverNames": [sni_host],
                        "privateKey": private_key,
                        "shortIds": [short_id]
                    }
                }
            },
            {
                "tag": "api",
                "listen": "0.0.0.0",
                "port": api_port,
                "protocol": "dokodemo-door",
                "settings": {"address": "127.0.0.1"}
            }
        ],
        "routing": {
            "rules": [
                {"type": "field", "inboundTag": ["api"], "outboundTag": "api"}
            ]
        },
        "outbounds": [
            {"protocol": "freedom"},
            {"tag": "api", "protocol": "blackhole"}
        ]
    }
    json.dump(config, sys.stdout, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
