"""Store the Fernet ENCRYPTION_KEY in the OS credential store.

Desktop installs used to write the key as plaintext into config.json, next to
ledger.db. Anyone who copied that folder could decrypt Plaid tokens. The OS
keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)
is bound to the logged-in OS user, so a copied database folder is no longer
enough — *after* we have verified the keychain round-trips and it is safe
to delete the file copy.

Fallback: if the keychain is missing or refuses the write (headless Linux,
locked keyring, user clicked Deny), we still use config.json so the app can
launch. A warning is logged.

Unsigned macOS builds: Keychain ACLs follow the code signature. Ledger ships
unsigned, so an app update can look like a different binary and Keychain will
prompt again (or refuse). We therefore keep config.json as a recovery copy
until the running binary has a stable Developer ID signature. Windows and
Linux strip the file after a verified write.

Tests call use_memory_backend() so they never touch the real keychain.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from typing import Optional

logger = logging.getLogger("ledger")

SERVICE = "com.ledger.desktop"
ACCOUNT = "encryption-key"

_memory: dict[tuple[str, str], str] = {}
_use_memory = False
_backend_ready = False
_signed_cache: Optional[bool] = None


def use_memory_backend() -> None:
    """In-process dict instead of the OS keychain. Tests only. Clears state."""
    global _use_memory, _backend_ready
    _use_memory = True
    _backend_ready = False
    _memory.clear()


def _primary_account() -> str:
    """Stable name in production; path-qualified when LEDGER_APPDATA isolates tests/profiles."""
    override = os.environ.get("LEDGER_APPDATA", "").strip()
    if override:
        from app import paths

        return f"{ACCOUNT}:{paths.app_data_dir().resolve()}"
    return ACCOUNT


def _legacy_account() -> str:
    """Path-qualified name used by the first revision of this feature."""
    from app import paths

    return f"{ACCOUNT}:{paths.app_data_dir().resolve()}"


def _accounts() -> list[str]:
    primary = _primary_account()
    legacy = _legacy_account()
    if primary == legacy:
        return [primary]
    return [primary, legacy]


def _ensure_os_backend() -> None:
    """Pin the native backend.

    Frozen PyInstaller builds often miss keyring's entry points, so auto-detect
    returns the fail backend and every write silently falls back to config.json.
    """
    global _backend_ready
    if _backend_ready or _use_memory:
        return
    _backend_ready = True
    try:
        import keyring
    except Exception:
        logger.debug("keyring import failed", exc_info=True)
        return
    try:
        if sys.platform == "darwin":
            from keyring.backends.macOS import Keyring

            keyring.set_keyring(Keyring())
        elif os.name == "nt":
            from keyring.backends.Windows import WinVaultKeyring

            keyring.set_keyring(WinVaultKeyring())
        else:
            try:
                from keyring.backends.libsecret import Keyring as LibsecretKeyring

                backend = LibsecretKeyring()
                backend.priority  # raises if the platform service is missing
                keyring.set_keyring(backend)
            except Exception:
                from keyring.backends.SecretService import Keyring as SecretServiceKeyring

                backend = SecretServiceKeyring()
                backend.priority
                keyring.set_keyring(backend)
    except Exception:
        logger.debug("Could not pin OS keyring backend; using keyring auto-detect", exc_info=True)


def _os_get(service: str, account: str) -> Optional[str]:
    import keyring

    _ensure_os_backend()
    return keyring.get_password(service, account)


def _os_set(service: str, account: str, password: str) -> None:
    import keyring

    _ensure_os_backend()
    keyring.set_password(service, account, password)


def get_os_key() -> Optional[str]:
    for account in _accounts():
        if _use_memory:
            val = _memory.get((SERVICE, account))
        else:
            try:
                val = _os_get(SERVICE, account)
            except Exception:
                logger.debug("OS keychain read failed", exc_info=True)
                continue
        if val:
            return val
    return None


def set_os_key(key: str) -> bool:
    """Return True if the keychain accepted the secret *and* a follow-up read matches."""
    account = _primary_account()
    if _use_memory:
        _memory[(SERVICE, account)] = key
        return True
    try:
        _os_set(SERVICE, account, key)
    except Exception:
        logger.warning(
            "OS keychain is unavailable; ENCRYPTION_KEY will be stored in config.json. "
            "A copy of the Ledger data folder would then include the key.",
            exc_info=True,
        )
        return False
    try:
        stored = _os_get(SERVICE, account)
    except Exception:
        logger.warning(
            "OS keychain write succeeded but the follow-up read failed; "
            "keeping ENCRYPTION_KEY in config.json.",
            exc_info=True,
        )
        return False
    if stored != key:
        logger.warning(
            "OS keychain round-trip did not return the key we stored; "
            "keeping ENCRYPTION_KEY in config.json."
        )
        return False
    return True


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


def _macos_has_stable_signature() -> bool:
    """True when the running binary is Developer ID / App Store signed (not ad-hoc)."""
    global _signed_cache
    if _signed_cache is not None:
        return _signed_cache
    if sys.platform != "darwin":
        _signed_cache = True
        return True
    exe = sys.executable
    try:
        result = subprocess.run(
            ["codesign", "-dv", "--verbose=2", exe],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        _signed_cache = False
        return False
    text = f"{result.stdout or ''}{result.stderr or ''}"
    if result.returncode != 0:
        _signed_cache = False
        return False
    if "Signature=adhoc" in text or "code object is not signed" in text.lower():
        _signed_cache = False
        return False
    # A real signing identity lists an Authority; TeamIdentifier=not set is ad-hoc.
    if "TeamIdentifier=not set" in text:
        _signed_cache = False
        return False
    _signed_cache = "Authority=" in text
    return _signed_cache


def _should_strip_file() -> bool:
    """Delete the plaintext file copy only when keychain access will survive updates."""
    if _use_memory:
        return True
    if sys.platform == "darwin":
        return _macos_has_stable_signature()
    return True


def persist(key: str) -> None:
    """Write the key to the keychain, falling back to config.json."""
    if set_os_key(key) and _should_strip_file():
        strip_file_key()
        return
    write_file_key(key)


def load() -> Optional[str]:
    """Resolve the encryption key: keychain first, then config.json (and migrate).

    If both stores have a key and they disagree, the file copy wins. A leftover
    or colliding keychain item is more likely to be wrong than config.json from
    a previous Ledger version or a restored data folder. persist() then updates
    the keychain. We never delete the file copy until the two agree and a
    round-trip has succeeded.
    """
    stored = get_os_key()
    legacy = file_key()
    if stored and legacy:
        if stored != legacy:
            logger.warning(
                "ENCRYPTION_KEY in config.json does not match the OS keychain; "
                "using the file copy and updating the keychain."
            )
            persist(legacy)
            return legacy
        if _should_strip_file():
            strip_file_key()
        return stored
    if stored:
        return stored
    if not legacy:
        return None
    persist(legacy)
    return legacy
