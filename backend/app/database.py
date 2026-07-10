"""
Database setup and session management.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv
from app.models import Base
from app.sqlite_paths import resolve_sqlite_database_url

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL = resolve_sqlite_database_url(os.getenv("DATABASE_URL", "sqlite:///ledger.db"))

# Create engine
_is_sqlite = "sqlite" in DATABASE_URL
engine = create_engine(
    DATABASE_URL,
    # NullPool: every session.close() truly closes the SQLite connection instead
    # of returning it to a pool. This eliminates stale write-lock hold-overs between
    # requests — the main source of "database is locked" errors in local dev.
    # NullPool has no downside for SQLite (no connection overhead to amortise).
    poolclass=NullPool if _is_sqlite else None,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
    echo=False,
)

# Enable WAL mode for SQLite — dramatically reduces Windows file-locking issues
# by allowing concurrent reads while a write is in progress.
if _is_sqlite:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_conn, _):
        try:
            dbapi_conn.execute("PRAGMA busy_timeout=30000")
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass  # DB locked at startup (Windows); WAL set on next successful connection

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables, then patch any columns added to models.py since
    the table was first created (create_all only creates missing *tables*,
    never adds columns to ones that already exist)."""
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns():
    """
    Additive-only schema patch: add any model column missing from an
    existing table. This project has no migration tooling, so a column
    added to models.py otherwise silently diverges from the DB file on
    disk until someone deletes and recreates it. Never drops or alters
    existing columns.
    """
    if not _is_sqlite:
        return
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_cols:
                    continue
                col_type = column.type.compile(engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))


def get_db() -> Session:
    """Dependency injection for database session in FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
