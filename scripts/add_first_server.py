"""
Добавляет первый (или ещё один) Xray-сервер в таблицу servers из переменных .env.

Xray может быть на том же VDS, где бот (host=127.0.0.1), или на другом сервере —
важно, чтобы с машины, где запущен бот, был доступ по сети до host:grpc_port.

Запуск (из корня проекта):
  python scripts/add_first_server.py
"""
import os
import sys

# корень проекта в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

def main():
    name = (os.getenv("XRAY_SERVER_NAME") or "").strip()
    host = (os.getenv("XRAY_SERVER_HOST") or "").strip()
    grpc_port_s = (os.getenv("XRAY_GRPC_PORT") or "").strip()
    max_users_s = (os.getenv("XRAY_MAX_USERS") or "100").strip()
    vless_template = (os.getenv("VLESS_URL_TEMPLATE") or "").strip() or None

    if not name or not host or not grpc_port_s:
        print(
            "Задайте в .env: XRAY_SERVER_NAME, XRAY_SERVER_HOST, XRAY_GRPC_PORT.\n"
            "Опционально: XRAY_MAX_USERS (по умолчанию 200), VLESS_URL_TEMPLATE (шаблон ссылки с {uuid})."
        )
        sys.exit(1)

    try:
        grpc_port = int(grpc_port_s)
        max_users = int(max_users_s) if max_users_s else 100
    except ValueError:
        print("XRAY_GRPC_PORT и XRAY_MAX_USERS должны быть числами.")
        sys.exit(1)

    from db.session import SessionLocal
    from db.models import Server

    db = SessionLocal()
    try:
        existing = db.query(Server).filter(
            Server.host == host,
            Server.grpc_port == grpc_port,
        ).first()
        if existing:
            print(f"Сервер уже есть: {existing.name} ({existing.host}:{existing.grpc_port})")
            return
        s = Server(
            name=name,
            host=host,
            grpc_port=grpc_port,
            max_users=max_users,
            enabled=True,
            vless_url_template=vless_template,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        print(f"Добавлен сервер: {s.name} {s.host}:{s.grpc_port} (max_users={s.max_users})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
