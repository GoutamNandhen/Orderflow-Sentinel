import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DATA = ROOT / "backend" / "data"
DATA.mkdir(exist_ok=True)
url = os.getenv("DATABASE_URL", f'sqlite:///{(DATA / "orderflow.db").as_posix()}')
if url.startswith("postgres://"):
    url = "postgresql+psycopg://" + url[len("postgres://") :]
elif url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://") :]
is_sqlite = url.startswith("sqlite:")
engine = create_engine(
    url,
    connect_args=(
        {"check_same_thread": False, "timeout": 30}
        if is_sqlite
        else {"connect_timeout": 10, "prepare_threshold": None}
    ),
    **({} if is_sqlite else {"pool_pre_ping": True, "pool_size": 4, "max_overflow": 2}),
)


@event.listens_for(engine, "connect")
def pragmas(conn, _):
    if is_sqlite:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")


class Base(DeclarativeBase):
    pass


def now():
    return datetime.now(timezone.utc)


def stamp(value=None):
    return (value or now()).isoformat()


def dt(value):
    return datetime.fromisoformat(value)


@contextmanager
def transaction():
    # SQLite's single-writer lock also serializes worker/operator races.
    with Session(engine, expire_on_commit=False) as session:
        if engine.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        else:
            # PostgreSQL equivalent of the local single-writer transaction contract.
            session.execute(text("SELECT pg_advisory_xact_lock(1330791494)"))
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
