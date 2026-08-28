"""App-data bootstrap. MUST run before any module that reads env at
import time (app.security, app.database, app.budgets_db).

Active when either:
  - LEDGER_DESKTOP=1  — packaged Tauri app (may generate a first-run key)
  - LEDGER_USE_APPDATA=1 — local uvicorn/Vite against the desktop DBs
    (requires an existing key; never invents a new one)

Otherwise this is a no-op so plain source installs keep using backend/.env
and backend/*.db.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

from app import paths


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def _desktop_enabled() -> bool:
    return _env_flag("LEDGER_DESKTOP")


def _use_appdata_enabled() -> bool:
    """Dev: point source uvicorn at the desktop Application Support DBs."""
    return _env_flag("LEDGER_USE_APPDATA")


def _sqlite_url(db_path) -> str:
    """Absolute sqlite URL. Keep spaces as spaces (sqlite3 needs a real path)."""
    return f"sqlite:///{db_path.resolve().as_posix()}"


def _setenv_default(key: str, value: str) -> None:
    """Set env only if not already present (preset env wins)."""
    if not os.environ.get(key):
        os.environ[key] = value


def _setenv_force(key: str, value: str) -> None:
    """Always set — used by LEDGER_USE_APPDATA so backend/.env cannot win."""
    os.environ[key] = value


def bootstrap_desktop() -> None:
    desktop = _desktop_enabled()
    use_appdata = _use_appdata_enabled()
    if not desktop and not use_appdata:
        return

    paths.app_data_dir()  # ensure dir (0700)

    from app import key_store

    key = key_store.load()

    if not key:
        if paths.ledger_db_path().exists():
            raise RuntimeError(
                "Existing ledger.db found but no ENCRYPTION_KEY in the OS keychain "
                "or config.json. Refusing to generate a new key (it would make stored "
                "Plaid tokens undecryptable). Restore the original key from Time Machine "
                "/ an old config.json, or look in Keychain Access (macOS, service "
                "com.ledger.desktop) / Credential Manager (Windows) / Secret Service "
                "(Linux), then re-import if needed."
            )
        if use_appdata and not desktop:
            # Dev mode must attach to an existing desktop install — never
            # silently create a fresh key/empty DB in Application Support.
            raise RuntimeError(
                "LEDGER_USE_APPDATA=1 but no ENCRYPTION_KEY in the OS keychain or "
                f"{paths.config_path()}. Quit the desktop app after first "
                "launch (so the key exists), or set ENCRYPTION_KEY yourself."
            )
        key = Fernet.generate_key().decode()
        key_store.persist(key)

    ledger_url = _sqlite_url(paths.ledger_db_path())
    budgets_url = _sqlite_url(paths.budgets_db_path())

    if use_appdata and not desktop:
        # Force — otherwise a DATABASE_URL in backend/.env silently keeps
        # uvicorn on the stale backend/ledger.db (e.g. "last synced Jul 9").
        _setenv_force("ENCRYPTION_KEY", key)
        _setenv_force("DATABASE_URL", ledger_url)
        _setenv_force("BUDGETS_DATABASE_URL", budgets_url)
        print(
            f"[LEDGER_USE_APPDATA] Using desktop DBs:\n"
            f"  ledger:  {paths.ledger_db_path()}\n"
            f"  budgets: {paths.budgets_db_path()}\n"
            f"  Quit the desktop app while this server is running."
        )
    else:
        _setenv_default("ENCRYPTION_KEY", key)
        _setenv_default("DATABASE_URL", ledger_url)
        _setenv_default("BUDGETS_DATABASE_URL", budgets_url)
