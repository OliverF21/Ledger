"""
Read-only database access for the analytics MCP server.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.sqlite_paths import BACKEND_DIR, resolve_sqlite_database_url

DEFAULT_LEDGER_DB = BACKEND_DIR / "ledger.db"
DEFAULT_BUDGETS_DB = BACKEND_DIR / "budgets.db"

# Claude/Cursor can launch the MCP server outside the backend shell session, so
# load the backend env file explicitly instead of relying on app.database being
# imported first as an indirect side effect.
load_dotenv(BACKEND_DIR / ".env")


def _env_database_url(name: str, default_filename: str) -> str:
    return resolve_sqlite_database_url(os.getenv(name, f"sqlite:///{default_filename}"))


def _resolve_sqlite_path(db_url: str, fallback: Path) -> Path | None:
    if not db_url.startswith("sqlite:///"):
        return None

    resolved = resolve_sqlite_database_url(db_url)
    return Path(resolved.removeprefix("sqlite:///"))


def _sqlite_read_only_engine(db_path: Path) -> Engine:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database file not found: {db_path}")

    def _connect() -> sqlite3.Connection:
        return sqlite3.connect(
            f"file:{db_path.as_posix()}?mode=ro",
            uri=True,
            check_same_thread=False,
            timeout=30,
        )

    engine = create_engine(
        "sqlite://",
        creator=_connect,
        poolclass=NullPool,
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _set_read_only_pragmas(dbapi_conn: sqlite3.Connection, _) -> None:
        dbapi_conn.execute("PRAGMA busy_timeout=30000")
        dbapi_conn.execute("PRAGMA query_only=1")

    return engine


def _build_engine(db_url: str, fallback: Path) -> Engine:
    sqlite_path = _resolve_sqlite_path(db_url, fallback)
    if sqlite_path is not None:
        return _sqlite_read_only_engine(sqlite_path)

    # Non-SQLite deployments are outside the local DB-file use case but can
    # still be queried if DATABASE_URL points elsewhere.
    return create_engine(
        db_url,
        poolclass=NullPool,
        echo=False,
        pool_pre_ping=True,
    )


def ledger_database_path() -> str | None:
    sqlite_path = _resolve_sqlite_path(_env_database_url("DATABASE_URL", "ledger.db"), DEFAULT_LEDGER_DB)
    return str(sqlite_path) if sqlite_path is not None else None


def budgets_database_path() -> str | None:
    sqlite_path = _resolve_sqlite_path(
        _env_database_url("BUDGETS_DATABASE_URL", "budgets.db"),
        DEFAULT_BUDGETS_DB,
    )
    return str(sqlite_path) if sqlite_path is not None else None


_schema_ready = False
_ledger_session_factory: sessionmaker[Session] | None = None
_budgets_session_factory: sessionmaker[Session] | None = None


def ensure_local_schema() -> None:
    """
    Reuse the backend's additive schema bootstrap before read-only access.

    Local MCP clients can start before the FastAPI app has run `init_db()`,
    which means older SQLite files may be missing newer additive columns.
    Bootstrapping once here keeps the MCP reads compatible with the live app.
    """
    global _schema_ready

    if _schema_ready:
        return

    # app.database / app.budgets_db read DATABASE_URL at import time; pin absolute
    # SQLite paths before importing them so schema bootstrap hits the real files.
    os.environ["DATABASE_URL"] = _env_database_url("DATABASE_URL", "ledger.db")
    os.environ["BUDGETS_DATABASE_URL"] = _env_database_url("BUDGETS_DATABASE_URL", "budgets.db")

    from app.budgets_db import init_budgets_db
    from app.database import init_db

    init_db()
    init_budgets_db()
    _schema_ready = True


def _get_ledger_session_factory() -> sessionmaker[Session]:
    global _ledger_session_factory

    ensure_local_schema()
    if _ledger_session_factory is None:
        engine = _build_engine(_env_database_url("DATABASE_URL", "ledger.db"), DEFAULT_LEDGER_DB)
        _ledger_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _ledger_session_factory


def _get_budgets_session_factory() -> sessionmaker[Session]:
    global _budgets_session_factory

    ensure_local_schema()
    if _budgets_session_factory is None:
        engine = _build_engine(
            _env_database_url("BUDGETS_DATABASE_URL", "budgets.db"),
            DEFAULT_BUDGETS_DB,
        )
        _budgets_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _budgets_session_factory


@contextmanager
def ledger_session() -> Iterator[Session]:
    session = _get_ledger_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def budgets_session() -> Iterator[Session]:
    session = _get_budgets_session_factory()()
    try:
        yield session
    finally:
        session.close()
