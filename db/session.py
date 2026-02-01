from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bot.config import DATABASE_URL
from db.base import Base

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_engine():
    return engine


def get_session():
    return SessionLocal()
