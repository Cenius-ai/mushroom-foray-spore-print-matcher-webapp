"""SQLite engine, session factory and schema bootstrap.

The database is a file next to the app (`sqlite:///./foray.db` by default), so a
fresh clone boots with a working datastore. Schema creation and demo seeding run
on the normal boot path (`init_db`) as well as from `python3 seed.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import config
from models import Base

connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine: Engine = create_engine(config.DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """SQLite ignores foreign keys unless every connection turns them on."""
    if config.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_schema() -> None:
    Base.metadata.create_all(engine)


def init_db(seed: bool = True) -> None:
    """Create tables and idempotently seed demo data (safe to call repeatedly)."""
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    create_schema()
    if seed:
        from seed import seed_all

        seed_all()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed in `finally`."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
