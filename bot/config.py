import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://krot-ray.vercel.app")
API_URL = os.getenv("API_URL", "http://localhost:8000")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./krotray.db")# ЮKassa (Итерация 5) — strip() убирает пробелы и \r при копировании из .env
YOOKASSA_SHOP_ID = (os.getenv("YOOKASSA_SHOP_ID") or "").strip()
YOOKASSA_SECRET_KEY = (os.getenv("YOOKASSA_SECRET_KEY") or "").strip()
PAYMENT_RETURN_URL = (os.getenv("PAYMENT_RETURN_URL") or "").strip() or (os.getenv("MINI_APP_URL") or "https://krot-ray.vercel.app").strip()

# Xray gRPC (Итерация 6.1)
XRAY_INBOUND_TAG = (os.getenv("XRAY_INBOUND_TAG") or "vless-in").strip()

# VLESS-ссылка (Итерация 6.2): шаблон с плейсхолдером {uuid}
VLESS_URL_TEMPLATE = (os.getenv("VLESS_URL_TEMPLATE") or "").strip()