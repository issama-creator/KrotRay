"""FastAPI приложение для API Mini App."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router

app = FastAPI(title="KrotRay API", version="0.1.0")


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
