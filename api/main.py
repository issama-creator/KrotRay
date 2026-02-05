"""FastAPI приложение для API Mini App (Итерация 6.2: фоновая задача просроченных)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.expired_job import run_expired_subscriptions
from api.payments import router as payments_router
from api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_expired_subscriptions, "interval", minutes=5, id="expired_subs")
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="KrotRay API", version="0.1.0", lifespan=lifespan)


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mini App может быть на любом домене (Vercel, localhost)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(payments_router, prefix="/api/payments")
