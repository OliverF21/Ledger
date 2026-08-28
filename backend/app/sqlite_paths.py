"""
Resolve relative SQLite URLs against the backend directory.

Claude Desktop and other MCP hosts may launch Python with an unrelated cwd,
so sqlite:///ledger.db must not depend on the process working directory.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

BACKEND_DIR = Path(__file__).resolve().parent.parent


def resolve_sqlite_database_url(db_url: str) -> str:
    if not db_url.startswith("sqlite:///"):
        return db_url

    raw_path = db_url.removeprefix("sqlite:///")
    if raw_path.startswith("file:"):
        raw_path = raw_path.removeprefix("file:")
        raw_path = raw_path.split("?", maxsplit=1)[0]

    # Percent-encoded paths (e.g. Application%20Support) must become real
    # filesystem spaces — sqlite3 opens the literal string it is given.
    raw_path = unquote(raw_path)

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = BACKEND_DIR / candidate
    # Keep spaces as spaces. Do not re-percent-encode: create_engine passes
    # the path to sqlite3, which expects a real filesystem path.
    return f"sqlite:///{candidate.resolve().as_posix()}"
