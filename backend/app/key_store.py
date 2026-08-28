"""Store the Fernet ENCRYPTION_KEY in the OS credential store.

Desktop installs used to write the key as plaintext into config.json, next to
ledger.db. Anyone who copied that folder could decrypt Plaid tokens. The OS
keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)
is bound to the logged-in OS user, so a copied database folder is no longer
enough.

Fallback: if the keychain is missing or refuses the write (headless Linux,
locked keyring), we still use config.json so the app can launch. A warning
is logged.

Tests call use_memory_backend() so they never touch the real keychain.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger("ledger")

SERVICE = "com.ledger.desktop"

_memory: dict[tuple[str, str], str] = {}
_use_memory = False


def use_memory_backend() -> None:
    """In-process dict instead of the OS keychain. Tests only. Clears state."""
    global _use_memory
    _use_memory = True
    _memory.clear()


def _account() -> str:
    """One keychain item per app-data directory so profiles/tests don't clash."""
    from app import paths

    return f"encryption-key:{paths.app_data_dir().resolve()}"


def _os_get(service: str, account: str) -> Optional[str]:
    import keyring

    return keyring.get_password(service, account)


def _os_set(service: str, account: str, password: str) -> None:
    import keyring

    keyring.set_password(service, account, password)


def get_os_key() -> Optional[str]:
    account = _account()
    if _use_memory:
        return _memory.get((SERVICE, account))
    try:
        val = _os_get(SERVICE, account)
        return val or None
    except Exception:
        logger.debug("OS keychain read failed", exc_info=True)
        return None


def set_os_key(key: str) -> bool:
    """Return True if the keychain accepted the secret."""
    account = _account()
    if _use_memory:
        _memory[(SERVICE, account)] = key
        return True
    try:
        _os_set(SERVICE, account, key)
        return True
    except Exception:
        logger.warning(
            "OS keychain is unavailable; ENCRYPTION_KEY will be stored in config.json. "
            "A copy of the Ledger data folder would then include the key.",
            exc_info=True,
        )
        return False


def _load_config() -> dict:
    from app import paths

    p = paths.config_path()
    if p.exists():
        try:
            data = json.loads(p.read_text())
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_config(cfg: dict) -> None:
    from app import paths

    p = paths.config_path()
    p.write_text(json.dumps(cfg, indent=2))
    if os.name == "posix":
        try:
            p.chmod(0o600)
        except OSError:
            pass


def file_key() -> Optional[str]:
    raw = _load_config().get("ENCRYPTION_KEY")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def strip_file_key() -> None:
    """Remove ENCRYPTION_KEY from config.json after a successful keychain write."""
    from app import paths

    cfg = _load_config()
    if "ENCRYPTION_KEY" not in cfg:
        return
    cfg.pop("ENCRYPTION_KEY", None)
    if cfg:
        _write_config(cfg)
        return
    p = paths.config_path()
    if p.exists():
        try:
            p.unlink()
        except OSError:
            _write_config({})


def write_file_key(key: str) -> None:
    cfg = _load_config()
    cfg["ENCRYPTION_KEY"] = key
    _write_config(cfg)


def persist(key: str) -> None:
    """Write the key to the keychain, falling back to config.json."""
    if set_os_key(key):
        strip_file_key()
        return
    write_file_key(key)


def load() -> Optional[str]:
    """Resolve the encryption key: keychain first, then config.json (and migrate)."""
    stored = get_os_key()
    if stored:
        strip_file_key()
        return stored
    legacy = file_key()
    if not legacy:
        return None
    persist(legacy)
    return legacy
