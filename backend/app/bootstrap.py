"""Desktop-mode bootstrap. MUST run before any module that reads env at
import time (app.security, app.database, app.budgets_db).

No-op unless LEDGER_DESKTOP is set, so non-desktop behavior is unchanged.
"""

from __future__ import annotations

import json
import os

from cryptography.fernet import Fernet

from app import paths


def _desktop_enabled() -> bool:
    return os.environ.get("LEDGER_DESKTOP", "").strip().lower() in {"1", "true", "yes"}


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
    if not _desktop_enabled():
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
        key = Fernet.generate_key().decode()
        cfg["ENCRYPTION_KEY"] = key
        _write_config(cfg)

    _setenv_default("ENCRYPTION_KEY", key)
    _setenv_default("DATABASE_URL", f"sqlite:///{paths.ledger_db_path()}")
    _setenv_default("BUDGETS_DATABASE_URL", f"sqlite:///{paths.budgets_db_path()}")
