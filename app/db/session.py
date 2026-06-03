"""SQLAlchemy engine + session wiring."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

engine = create_engine(_settings.sqlalchemy_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_schema() -> None:
    """Create all tables if they don't exist. Called on app startup."""
    from app.db import models  # noqa: F401 — ensure models are registered

    models.Base.metadata.create_all(bind=engine)
