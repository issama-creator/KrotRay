from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.key_factory_api import router as key_factory_router
from api.payments import router as payments_router


app = FastAPI(title="KrotRay Key Factory API", version="1.0.0")


@app.get("/")
def root():
    return {"status": "ok", "service": "key-factory", "docs": "/docs"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(key_factory_router)
app.include_router(payments_router, prefix="/api/payments")
