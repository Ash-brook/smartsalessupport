"""Database engine and session setup.

Uses SQLite in WAL (Write-Ahead Logging) mode so the async pipeline runner and the
API can read/write the single database file without blocking each other as much.
"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings


class Base(DeclarativeBase):
    """Base class all ORM models inherit from."""


# Resolve the sqlite file path relative to the project root and make sure data/ exists.
if settings.database_url.startswith("sqlite:///"):
    db_path = Path(settings.database_url.replace("sqlite:///", "", 1))
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    # SQLite + multithreading: the pipeline runner and API touch the same connection pool.
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_wal(dbapi_connection, _connection_record):
    """Turn on WAL mode and sane pragmas for every new SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session and always closes it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
