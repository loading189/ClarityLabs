from __future__ import annotations

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()


def _get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL or SQLALCHEMY_DATABASE_URL must be set to create the database engine."
        )
    return database_url


def _build_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, future=True, connect_args=connect_args)


DATABASE_URL = _get_database_url()
engine = _build_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
