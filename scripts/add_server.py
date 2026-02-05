"""
Добавляет ещё один Xray-сервер в таблицу servers (то же, что add_first_server.py).

Для каждого нового сервера: поменяй в .env XRAY_SERVER_* и VLESS_URL_TEMPLATE, затем запусти:
  python scripts/add_server.py
  (или python scripts/add_first_server.py)

Дубликаты по host+grpc_port не создаются.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from scripts.add_first_server import main

if __name__ == "__main__":
    main()
