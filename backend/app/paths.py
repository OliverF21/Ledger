"""Resolve the per-OS application-data directory for desktop mode.

Databases and the generated encryption key live here (never inside the
install dir, so app updates don't wipe user data). Set LEDGER_APPDATA to
override (tests, custom locations).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Ledger"


def _default_base() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        return Path(base) if base else Path.home() / "AppData" / "Roaming"
    # Linux / other: XDG data home
    xdg = os.environ.get("XDG_DATA_HOME")
    return Path(xdg) if xdg else Path.home() / ".local" / "share"


def app_data_dir() -> Path:
    override = os.environ.get("LEDGER_APPDATA")
    d = Path(override) if override else _default_base() / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        try:
            d.chmod(0o700)
        except OSError:
            pass
    return d


def config_path() -> Path:
    return app_data_dir() / "config.json"


def ledger_db_path() -> Path:
    return app_data_dir() / "ledger.db"


def budgets_db_path() -> Path:
    return app_data_dir() / "budgets.db"
