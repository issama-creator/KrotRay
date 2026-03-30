"""Добавить узел в cp_servers (VPN data plane). Пример:

python scripts/add_cp_server.py --ip 1.2.3.4 --role nl --public-key PK --short-id sid --sni www.example.com
"""
from __future__ import annotations

import argparse

from db.models.cp_server import CpServer
from db.session import SessionLocal


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ip", required=True)
    p.add_argument("--role", required=True, choices=("nl", "standard_bridge", "bypass_bridge"))
    p.add_argument("--public-key", required=True, dest="public_key")
    p.add_argument("--short-id", required=True, dest="short_id")
    p.add_argument("--sni", required=True)
    p.add_argument("--path", default="/")
    p.add_argument("--max-users", type=int, default=100, dest="max_users")
    args = p.parse_args()

    db = SessionLocal()
    try:
        srv = CpServer(
            ip=args.ip,
            role=args.role,
            public_key=args.public_key,
            short_id=args.short_id,
            sni=args.sni,
            path=args.path,
            max_users=args.max_users,
            current_users=0,
            latency=None,
            active=True,
        )
        db.add(srv)
        db.commit()
        db.refresh(srv)
        print(f"cp_servers id={srv.id} role={srv.role} ip={srv.ip}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
