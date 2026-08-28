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

Unsigned macOS: default Keychain ACLs follow the creating binary's signature,
so an update can look like a different app. We store the item with an
"any application in this login session" ACL (same local-user trust as the old
config.json file) so unsigned updates can still read it, then delete the file.
A copied Application Support folder no longer includes the key.

Tests call use_memory_backend() so they never touch the real keychain.
"""

from __future__ import annotations

import contextlib
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
_last_write_used_open_acl = False


def use_memory_backend() -> None:
    """In-process dict instead of the OS keychain. Tests only. Clears state."""
    global _use_memory, _backend_ready, _last_write_used_open_acl
    _use_memory = True
    _backend_ready = False
    _last_write_used_open_acl = False
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


def _cf_release(ref) -> None:
    if not ref:
        return
    try:
        from ctypes import c_void_p, CDLL
        from ctypes.util import find_library

        cf = CDLL(find_library("CoreFoundation"))
        cf.CFRelease.argtypes = [c_void_p]
        cf.CFRelease.restype = None
        ptr = ref if isinstance(ref, int) else getattr(ref, "value", ref)
        if ptr:
            cf.CFRelease(c_void_p(ptr) if not isinstance(ref, c_void_p) else ref)
    except Exception:
        logger.debug("CFRelease failed", exc_info=True)


def _darwin_create_any_app_access():
    """SecAccessRef allowing every app in this login session to read the item.

    Passing a NULL path to SecTrustedApplicationCreateFromPath means "all
    applications". That is what makes unsigned Ledger updates able to read the
    key without a Developer ID certificate. Other processes running as you can
    also read it — the same trust model as a 0600 config.json in your home
    folder, but the secret no longer sits next to ledger.db.
    """
    from ctypes import (
        CDLL,
        POINTER,
        byref,
        c_char_p,
        c_int32,
        c_long,
        c_void_p,
    )
    from ctypes.util import find_library

    sec_path = find_library("Security")
    cf_path = find_library("CoreFoundation")
    if not sec_path or not cf_path:
        raise RuntimeError("Security/CoreFoundation not available")

    sec = CDLL(sec_path)
    cf = CDLL(cf_path)

    sec.SecTrustedApplicationCreateFromPath.argtypes = [c_char_p, POINTER(c_void_p)]
    sec.SecTrustedApplicationCreateFromPath.restype = c_int32
    sec.SecAccessCreate.argtypes = [c_void_p, c_void_p, POINTER(c_void_p)]
    sec.SecAccessCreate.restype = c_int32
    cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_int32]
    cf.CFStringCreateWithCString.restype = c_void_p
    cf.CFArrayCreate.argtypes = [c_void_p, c_void_p, c_long, c_void_p]
    cf.CFArrayCreate.restype = c_void_p
    cf.CFRelease.argtypes = [c_void_p]
    cf.CFRelease.restype = None

    trusted = c_void_p()
    status = sec.SecTrustedApplicationCreateFromPath(None, byref(trusted))
    if status != 0 or not trusted.value:
        raise RuntimeError(f"SecTrustedApplicationCreateFromPath failed: {status}")

    desc = cf.CFStringCreateWithCString(None, b"Ledger encryption key", 0x08000100)
    callbacks = c_void_p.in_dll(cf, "kCFTypeArrayCallBacks")
    values = (c_void_p * 1)(trusted)
    arr = cf.CFArrayCreate(None, values, 1, callbacks)
    if not desc or not arr:
        if trusted.value:
            cf.CFRelease(trusted)
        if desc:
            cf.CFRelease(c_void_p(desc))
        if arr:
            cf.CFRelease(c_void_p(arr))
        raise RuntimeError("CFString/CFArray create failed")

    access = c_void_p()
    status = sec.SecAccessCreate(c_void_p(desc), c_void_p(arr), byref(access))
    cf.CFRelease(c_void_p(desc))
    cf.CFRelease(c_void_p(arr))
    cf.CFRelease(trusted)
    if status != 0 or not access.value:
        raise RuntimeError(f"SecAccessCreate failed: {status}")
    return access


def _darwin_set_open_acl(service: str, account: str, password: str) -> None:
    """Write the generic password with an any-app ACL so unsigned updates still work."""
    global _last_write_used_open_acl
    from keyring.backends.macOS import api as mac_api

    access = _darwin_create_any_app_access()
    try:
        with contextlib.suppress(mac_api.NotFound):
            mac_api.delete_generic_password(None, service, account)
        query = mac_api.create_query(
            kSecClass=mac_api.k_("kSecClassGenericPassword"),
            kSecAttrService=service,
            kSecAttrAccount=account,
            kSecValueData=password,
            kSecAttrAccess=access,
        )
        status = mac_api.SecItemAdd(query, None)
        mac_api.Error.raise_for_status(status)
        _last_write_used_open_acl = True
    finally:
        _cf_release(access)


def _darwin_ensure_open_acl(service: str, account: str) -> bool:
    """Point an existing item's ACL at every app. Returns True on success.

    Used before deleting config.json so a later unsigned binary can still read
    a key that was originally stored with the default (binary-bound) ACL.
    """
    if sys.platform != "darwin":
        return False
    try:
        from ctypes import CDLL, POINTER, byref, c_char_p, c_int32, c_uint32, c_void_p
        from ctypes.util import find_library

        sec_path = find_library("Security")
        if not sec_path:
            return False
        sec = CDLL(sec_path)
        sec.SecKeychainFindGenericPassword.argtypes = [
            c_void_p,
            c_uint32,
            c_char_p,
            c_uint32,
            c_char_p,
            c_void_p,
            c_void_p,
            POINTER(c_void_p),
        ]
        sec.SecKeychainFindGenericPassword.restype = c_int32
        sec.SecKeychainItemSetAccess.argtypes = [c_void_p, c_void_p]
        sec.SecKeychainItemSetAccess.restype = c_int32

        svc = service.encode("utf-8")
        acct = account.encode("utf-8")
        item = c_void_p()
        status = sec.SecKeychainFindGenericPassword(
            None,
            len(svc),
            svc,
            len(acct),
            acct,
            None,
            None,
            byref(item),
        )
        if status != 0 or not item.value:
            logger.debug("Keychain item not found for ACL update (%s)", status)
            return False

        access = _darwin_create_any_app_access()
        try:
            set_status = sec.SecKeychainItemSetAccess(item, access)
        finally:
            _cf_release(access)
            _cf_release(item)
        if set_status != 0:
            logger.warning(
                "Could not mark the Keychain item as readable after unsigned updates "
                "(status %s); keeping ENCRYPTION_KEY in config.json.",
                set_status,
            )
            return False
        return True
    except Exception:
        logger.warning(
            "Could not mark the Keychain item as readable after unsigned updates; "
            "keeping ENCRYPTION_KEY in config.json.",
            exc_info=True,
        )
        return False


def _os_get(service: str, account: str) -> Optional[str]:
    import keyring

    _ensure_os_backend()
    return keyring.get_password(service, account)


def _os_set(service: str, account: str, password: str) -> None:
    global _last_write_used_open_acl
    import keyring

    _ensure_os_backend()
    _last_write_used_open_acl = False
    if sys.platform == "darwin" and not _macos_has_stable_signature():
        _darwin_set_open_acl(service, account, password)
        return
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
    if "TeamIdentifier=not set" in text:
        _signed_cache = False
        return False
    _signed_cache = "Authority=" in text
    return _signed_cache


def _safe_to_drop_file_copy() -> bool:
    """Delete the plaintext file copy only when keychain access will survive updates."""
    if _use_memory:
        return True
    if sys.platform != "darwin":
        return True
    if _macos_has_stable_signature():
        return True
    if _last_write_used_open_acl:
        return True
    # Unsigned: only drop the file once the item is readable by any app
    # in this login session (so the next Ledger build can still read it).
    return _darwin_ensure_open_acl(SERVICE, _primary_account())


def persist(key: str) -> None:
    """Write the key to the keychain, falling back to config.json."""
    if set_os_key(key) and _safe_to_drop_file_copy():
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
        if _safe_to_drop_file_copy():
            strip_file_key()
        return stored
    if stored:
        return stored
    if not legacy:
        return None
    persist(legacy)
    return legacy
