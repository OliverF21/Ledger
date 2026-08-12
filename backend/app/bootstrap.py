"""App-data bootstrap. MUST run before any module that reads env at
import time (app.security, app.database, app.budgets_db).

Active when either:
  - LEDGER_DESKTOP=1  — packaged Tauri app (may generate a first-run key)
  - LEDGER_USE_APPDATA=1 — local uvicorn/Vite against the desktop DBs
    (requires an existing config.json; never invents a new key)

Otherwise this is a no-op so plain source installs keep using backend/.env
and backend/*.db.
"""

from __future__ import annotations

import json
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


def _load_config() -> dict:
    p = paths.config_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_config(cfg: dict) -> None:
    p = paths.config_path()
    p.write_text(json.dumps(cfg, indent=2))
    if os.name == "posix":
        try:
            p.chmod(0o600)
        except OSError:
            pass


def _setenv_default(key: str, value: str) -> None:
    """Set env only if not already present (preset env wins)."""
    if not os.environ.get(key):
        os.environ[key] = value


def bootstrap_desktop() -> None:
    desktop = _desktop_enabled()
    use_appdata = _use_appdata_enabled()
    if not desktop and not use_appdata:
        return

    paths.app_data_dir()  # ensure dir (0700)
    cfg = _load_config()
    key = cfg.get("ENCRYPTION_KEY")

    if not key:
        if paths.ledger_db_path().exists():
            raise RuntimeError(
                "Existing ledger.db found but no ENCRYPTION_KEY in config.json. "
                "Refusing to generate a new key (it would make stored Plaid "
                "tokens undecryptable). Restore the original key or re-import."
            )
        if use_appdata and not desktop:
            # Dev mode must attach to an existing desktop install — never
            # silently create a fresh key/empty DB in Application Support.
            raise RuntimeError(
                "LEDGER_USE_APPDATA=1 but no ENCRYPTION_KEY in "
                f"{paths.config_path()}. Quit the desktop app after first "
                "launch (so config.json exists), or set ENCRYPTION_KEY yourself."
            )
        key = Fernet.generate_key().decode()
        cfg["ENCRYPTION_KEY"] = key
        _write_config(cfg)

    _setenv_default("ENCRYPTION_KEY", key)
    _setenv_default("DATABASE_URL", f"sqlite:///{paths.ledger_db_path()}")
    _setenv_default("BUDGETS_DATABASE_URL", f"sqlite:///{paths.budgets_db_path()}")
