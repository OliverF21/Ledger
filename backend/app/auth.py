"""
Authentication for the Ledger backend.

Two accepted credentials on every /api route (see require_auth):
  - Authorization: Bearer <session-token>  — the normal path, issued by
    /api/auth/login and /api/auth/register.
  - X-API-Key: <API_KEY>                    — legacy/automation path, only
    active when API_KEY is set in the environment.

Session tokens are Fernet-encrypted+signed blobs carrying the user id and an
issued-at timestamp, with a TTL. The signing key is derived from
ENCRYPTION_KEY via HMAC (distinct context) so a leaked session key can never
decrypt stored Plaid access tokens, and vice versa. Set AUTH_TOKEN_KEY to
decouple the two entirely (e.g. to rotate ENCRYPTION_KEY without logging
everyone out).

Passwords are hashed with stdlib hashlib.scrypt — no third-party deps.
"""

import base64
import hashlib
import hmac
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Header, HTTPException

logger = logging.getLogger("ledger")

# Optional legacy shared secret. When unset, only Bearer tokens are accepted.
API_KEY = os.getenv("API_KEY")

# Scoped, create-only key for the MCP server's propose_* tools. Accepted ONLY on
# POST /api/proposals (see require_proposal_service) — deliberately narrower than
# API_KEY, which authenticates every /api route. A leaked proposal key can stage
# a suggestion for the user to review; it can never sync, categorize, or apply.
#
# Historically read once at import time, but the guided AI Advisor setup lets a
# desktop user generate/store this in app_config from Settings without a
# restart, so require_proposal_service now resolves it dynamically on every
# request (see _proposal_service_key below). This module-level constant is
# unused by require_proposal_service; kept only so existing tests/imports that
# reference app.auth.PROPOSAL_SERVICE_KEY don't break.
PROPOSAL_SERVICE_KEY = os.getenv("PROPOSAL_SERVICE_KEY")


def _proposal_service_key() -> str | None:
    """Resolve the effective proposal service key: app_config table first
    (desktop BYOK, generated via Settings > AI Advisor), os.getenv fallback
    second. Mirrors PlaidService._setting / email_sender._setting."""
    try:
        from app.database import SessionLocal
        from app import app_config
        db = SessionLocal()
        try:
            val = app_config.get(db, "PROPOSAL_SERVICE_KEY")
        finally:
            db.close()
        if val:
            return val
    except Exception:
        logger.debug("app_config lookup failed for PROPOSAL_SERVICE_KEY; falling back to env", exc_info=True)
    return os.getenv("PROPOSAL_SERVICE_KEY")

SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))
_SESSION_TTL_SECONDS = SESSION_TTL_DAYS * 86400

# scrypt parameters (RFC 7914). N must be a power of 2.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def _session_key() -> bytes:
    """Fernet key for session tokens, derived from ENCRYPTION_KEY (or an
    explicit AUTH_TOKEN_KEY override) so it's isolated from Plaid-token
    encryption."""
    override = os.getenv("AUTH_TOKEN_KEY")
    if override:
        return override.encode()
    base = os.getenv("ENCRYPTION_KEY", "").encode()
    digest = hmac.new(base, b"ledger-session-v1", hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest)


def _cipher() -> Fernet:
    return Fernet(_session_key())


# ── Session tokens ──────────────────────────────────────────────────────────

def create_session_token(user_id: int) -> str:
    """Issue an opaque session token for the given user id."""
    return _cipher().encrypt(str(user_id).encode()).decode()


def verify_session_token(token: str) -> int | None:
    """Return the user id if the token is valid and unexpired, else None."""
    if not token:
        return None
    try:
        raw = _cipher().decrypt(token.encode(), ttl=_SESSION_TTL_SECONDS)
        return int(raw.decode())
    except (InvalidToken, ValueError):
        return None


# ── Password hashing ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password with scrypt. Format: scrypt$N$r$p$salt_b64$hash_b64."""
    salt = os.urandom(16)
    derived = hashlib.scrypt(
        password.encode(), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode(),
        base64.b64encode(derived).decode(),
    )


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time verify a password against a stored scrypt hash."""
    if not stored:
        return False
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        derived = hashlib.scrypt(
            password.encode(), salt=salt,
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
        return hmac.compare_digest(derived, expected)
    except (ValueError, TypeError):
        return False


# ── Recovery code (local "forgot password" — no email transport required) ───
#
# Single-user, no reliably-configured email transport, so password recovery
# can't be email-based. Instead: a one-time-displayed code, hashed the same
# way as the password (hash_password/verify_password work on any string).
# Excludes visually-ambiguous characters (0/O, 1/I/L) since it's hand-typed.
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_recovery_code() -> str:
    """A fresh recovery code, formatted XXXX-XXXX-XXXX for readability."""
    import secrets
    raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(12))
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def normalize_recovery_code(code: str) -> str:
    """Uppercase + strip whitespace/dashes so pasted codes match regardless of
    formatting."""
    return "".join(code.split()).replace("-", "").upper()


# ── Request dependency ──────────────────────────────────────────────────────

def require_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    """FastAPI dependency: accept a valid Bearer session token or, if API_KEY
    is configured, a matching X-API-Key. Raise 401 otherwise."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if verify_session_token(token) is not None:
            return

    if API_KEY and x_api_key and hmac.compare_digest(x_api_key, API_KEY):
        return

    raise HTTPException(status_code=401, detail="Not authenticated")


def require_proposal_service(
    x_proposal_key: str | None = Header(default=None),
) -> None:
    """FastAPI dependency for POST /api/proposals only: accept a matching
    X-Proposal-Key. This is the MCP server's create-only credential — it does
    NOT grant access to any other route. Raise 401/503 otherwise."""
    effective_key = _proposal_service_key()
    if not effective_key:
        # Not configured → the propose path is disabled rather than open.
        raise HTTPException(
            status_code=503,
            detail="Proposal service key not configured (set PROPOSAL_SERVICE_KEY)",
        )
    if x_proposal_key and hmac.compare_digest(x_proposal_key, effective_key):
        return
    raise HTTPException(status_code=401, detail="Invalid proposal service key")
