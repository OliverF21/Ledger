"""
Unauthenticated auth + setup endpoints (mounted WITHOUT require_auth):
  - GET  /api/setup/status               — first-run detection + Plaid env-var presence
  - POST /api/auth/register              — claim the single-user account (first run only)
  - POST /api/auth/login                 — password login
  - POST /api/auth/reset-password        — reset via one-time recovery code
  - GET  /api/auth/reset-options         — whether email-based reset is available
  - POST /api/auth/forgot-password       — email a one-time reset code
  - POST /api/auth/reset-password-email  — reset via the emailed one-time code
  - POST /api/auth/continue-without-account — this computer, no password (loopback)
  - POST /api/auth/local-session         — reissue that session (loopback)
  - POST /api/auth/enable-account        — add a password later (current session)
  - GET  /api/auth/me                    — validate the current session token

Single-user model: registration and login both operate on the user id=1 row.
No-account mode never stores a password. A missing or expired token is replaced
by /api/auth/local-session, which only answers requests from this machine.
"""

import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import email_sender
from app.auth import (
    create_session_token,
    generate_recovery_code,
    generate_reset_code,
    hash_password,
    is_loopback_host,
    is_valid_email,
    request_client_host,
    mask_email,
    normalize_recovery_code,
    require_auth,
    verify_password,
)
from app.database import get_db
from app.errors import log_and_raise
from app.models import User

router = APIRouter(tags=["auth"])

MIN_PASSWORD_LENGTH = 8


def _get_user(db: Session) -> User:
    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = User(id=1, username="default_user")
        db.add(user)
        db.commit()
    return user


def _missing_plaid_vars() -> list[str]:
    """Names (never values) of required-but-unset Plaid env vars, mirroring
    plaid_service._get_credentials() selection by PLAID_ENV."""
    missing = []
    if not os.getenv("PLAID_CLIENT_ID"):
        missing.append("PLAID_CLIENT_ID")
    env = os.getenv("PLAID_ENV", "sandbox").lower()
    if env == "production":
        if not os.getenv("PLAID_PROD_SECRET"):
            missing.append("PLAID_PROD_SECRET")
    else:
        if not os.getenv("PLAID_SANDBOX_SECRET"):
            missing.append("PLAID_SANDBOX_SECRET")
    return missing


# ── Setup status ────────────────────────────────────────────────────────────

class SetupStatus(BaseModel):
    account_exists: bool
    # True when this install was opened with no password. The client renews
    # that session from loopback and does not show a login screen.
    local_only: bool = False
    plaid_env: str
    plaid_ok: bool
    missing_plaid_vars: list[str]


def _is_local_only(user: User | None) -> bool:
    """No password, and the user explicitly chose to skip creating an account."""
    return bool(user and user.local_only and not user.password_hash)


def _require_loopback(request: Request) -> None:
    peer = request.client.host if request.client else None
    host = request_client_host(peer, request.headers.get("x-forwarded-for"))
    if not is_loopback_host(host):
        raise HTTPException(
            status_code=403,
            detail="Continuing without an account is only available on this computer",
        )


@router.get("/setup/status", response_model=SetupStatus)
async def setup_status(db: Session = Depends(get_db)):
    """First-run + Plaid-config check for the login/loading screen."""
    try:
        user = db.query(User).filter(User.id == 1).first()
        missing = _missing_plaid_vars()
        return SetupStatus(
            account_exists=bool(user and user.password_hash),
            local_only=_is_local_only(user),
            plaid_env=os.getenv("PLAID_ENV", "sandbox").lower(),
            plaid_ok=not missing,
            missing_plaid_vars=missing,
        )
    except Exception as e:
        log_and_raise(e)


# ── Register / login ────────────────────────────────────────────────────────

class Credentials(BaseModel):
    username: str
    password: str


class RegisterBody(Credentials):
    # Friendly display name shown on the homepage header and in the weekly
    # email. Optional; falls back to the username when blank.
    name: str | None = None
    # Optional account recovery email (see routes/auth.py's forgot-password /
    # reset-password-email). Leaving it unset means the recovery-code flow
    # remains the only "forgot password" path.
    email: str | None = None


class AuthResult(BaseModel):
    token: str
    username: str
    # Only populated on register and reset-password — the ONE time the plaintext
    # code is available. Never returned by /auth/login or /auth/me.
    recovery_code: str | None = None


@router.post("/auth/register", response_model=AuthResult)
async def register(body: RegisterBody, db: Session = Depends(get_db)):
    """Create the single-user account (first run only). Issues a one-time
    recovery code — the fallback "forgot password" path when no recovery
    email is set, or the operator hasn't configured email-based reset."""
    try:
        user = _get_user(db)
        if user.password_hash:
            raise HTTPException(status_code=409, detail="An account already exists")
        if user.local_only:
            raise HTTPException(
                status_code=409,
                detail="This install is already open without an account",
            )
        username = body.username.strip()
        if not username:
            raise HTTPException(status_code=400, detail="Username is required")
        if len(body.password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
            )
        email = (body.email or "").strip()
        if email and not is_valid_email(email):
            raise HTTPException(status_code=400, detail="Invalid email address")
        user.username = username
        user.display_name = (body.name or "").strip() or None
        user.email = email or None
        user.password_hash = hash_password(body.password)
        recovery_code = generate_recovery_code()
        user.recovery_code_hash = hash_password(normalize_recovery_code(recovery_code))
        db.commit()
        return AuthResult(
            token=create_session_token(user.id),
            username=user.username,
            recovery_code=recovery_code,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e)


@router.post("/auth/login", response_model=AuthResult)
async def login(body: Credentials, db: Session = Depends(get_db)):
    """Password login."""
    try:
        user = db.query(User).filter(User.id == 1).first()
        if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        return AuthResult(token=create_session_token(user.id), username=user.username)
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e)


def _local_session_result(user: User) -> AuthResult:
    return AuthResult(
        token=create_session_token(user.id),
        username=user.username,
        recovery_code=None,
    )


@router.post("/auth/continue-without-account", response_model=AuthResult)
async def continue_without_account(request: Request, db: Session = Depends(get_db)):
    """Open Ledger on this computer with no password and no recovery code.

    Idempotent once chosen: a second call just issues a fresh session. Rejected
    once a password exists, and rejected from any peer that is not loopback —
    the API would otherwise be open to the network.
    """
    try:
        _require_loopback(request)
        user = _get_user(db)
        if user.password_hash:
            raise HTTPException(status_code=409, detail="An account already exists")
        user.local_only = True
        if not user.username:
            user.username = "default_user"
        db.commit()
        return _local_session_result(user)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e)


@router.post("/auth/local-session", response_model=AuthResult)
async def local_session(request: Request, db: Session = Depends(get_db)):
    """Reissue a session for an install that has no account.

    Called when the saved token is missing or expired. Does not create the
    no-account choice — that is continue-without-account, so a first launch
    still asks. Loopback only. 404 when a password is set or the choice has
    not been made, so the client falls through to the login screen.
    """
    try:
        _require_loopback(request)
        user = db.query(User).filter(User.id == 1).first()
        if not _is_local_only(user):
            raise HTTPException(status_code=404, detail="No-account access is not enabled")
        return _local_session_result(user)
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e)


class EnableAccountBody(BaseModel):
    username: str
    password: str
    name: str | None = None
    email: str | None = None


@router.post("/auth/enable-account", response_model=AuthResult, dependencies=[Depends(require_auth)])
async def enable_account(body: EnableAccountBody, db: Session = Depends(get_db)):
    """Add a password to an install that was opened without an account.

    Requires the current session, so a remote caller who never received a
    token cannot lock the owner out. Returns a one-time recovery code, same
    as registration.
    """
    try:
        user = db.query(User).filter(User.id == 1).first()
        if user and user.password_hash:
            raise HTTPException(status_code=409, detail="An account already exists")
        if not _is_local_only(user):
            raise HTTPException(status_code=409, detail="No-account access is not enabled")
        username = body.username.strip()
        if not username:
            raise HTTPException(status_code=400, detail="Username is required")
        if len(body.password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
            )
        email = (body.email or "").strip()
        if email and not is_valid_email(email):
            raise HTTPException(status_code=400, detail="Invalid email address")
        user.username = username
        user.display_name = (body.name or "").strip() or None
        user.email = email or None
        user.password_hash = hash_password(body.password)
        user.local_only = False
        recovery_code = generate_recovery_code()
        user.recovery_code_hash = hash_password(normalize_recovery_code(recovery_code))
        db.commit()
        return AuthResult(
            token=create_session_token(user.id),
            username=user.username,
            recovery_code=recovery_code,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e)


class ResetPasswordBody(BaseModel):
    recovery_code: str
    new_password: str


@router.post("/auth/reset-password", response_model=AuthResult)
async def reset_password(body: ResetPasswordBody, db: Session = Depends(get_db)):
    """Reset the password using the one-time recovery code, and issue a fresh
    code (the consumed one no longer works). This is the fallback "forgot
    password" path when email-based reset isn't set up — see
    reset_password_email() for the emailed one-time-code alternative."""
    try:
        user = db.query(User).filter(User.id == 1).first()
        if not user or not user.recovery_code_hash:
            raise HTTPException(status_code=400, detail="No recovery code is set for this account")
        if not verify_password(normalize_recovery_code(body.recovery_code), user.recovery_code_hash):
            raise HTTPException(status_code=401, detail="Invalid recovery code")
        if len(body.new_password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
            )
        user.password_hash = hash_password(body.new_password)
        new_code = generate_recovery_code()
        user.recovery_code_hash = hash_password(normalize_recovery_code(new_code))
        db.commit()
        return AuthResult(
            token=create_session_token(user.id),
            username=user.username,
            recovery_code=new_code,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e)


class ResetOptions(BaseModel):
    email_available: bool
    masked_email: str | None = None


@router.get("/auth/reset-options", response_model=ResetOptions)
async def reset_options(db: Session = Depends(get_db)):
    """Whether the emailed one-time-code reset path is usable right now:
    requires both an account email on file AND a BYOK password-reset Resend
    key (RESET_EMERGENCY_RESEND_API_KEY, set via Settings/setup or env — see
    email_sender.is_reset_email_configured()). Never requires the
    weekly-digest RESEND_API_KEY."""
    try:
        user = db.query(User).filter(User.id == 1).first()
        available = bool(user and user.email and email_sender.is_reset_email_configured())
        return ResetOptions(
            email_available=available,
            masked_email=mask_email(user.email) if available else None,
        )
    except Exception as e:
        log_and_raise(e)


class ForgotPasswordResult(BaseModel):
    sent: bool


RESET_CODE_TTL = timedelta(hours=1)


@router.post("/auth/forgot-password", response_model=ForgotPasswordResult)
async def forgot_password(db: Session = Depends(get_db)):
    """Email a one-time reset code to the account's on-file address, via the
    emergency Resend key. 400 if no email/key is configured (defense in
    depth — the UI should already hide this path via reset-options)."""
    try:
        user = db.query(User).filter(User.id == 1).first()
        if not user or not user.email or not email_sender.is_reset_email_configured():
            raise HTTPException(status_code=400, detail="Email-based reset is not available")

        code = generate_reset_code()
        user.reset_code_hash = hash_password(code)
        user.reset_code_expires_at = datetime.utcnow() + RESET_CODE_TTL
        db.commit()

        sent = email_sender.send_password_reset_email(
            user.email,
            "Your Ledger password reset code",
            f"<p>Your password reset code is <strong>{code}</strong>.</p>"
            f"<p>It expires in 1 hour. If you didn't request this, ignore this email.</p>",
        )
        if not sent:
            raise HTTPException(status_code=502, detail="Failed to send the reset email")
        return ForgotPasswordResult(sent=True)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e)


class ResetPasswordEmailBody(BaseModel):
    code: str
    new_password: str


@router.post("/auth/reset-password-email", response_model=AuthResult)
async def reset_password_email(body: ResetPasswordEmailBody, db: Session = Depends(get_db)):
    """Reset the password using the one-time emailed code. Mirrors
    reset_password (recovery-code path) in every way except the credential
    checked: verifies + clears reset_code_hash/expires_at instead of
    recovery_code_hash, and additionally checks expiry. Also rotates the
    recovery code, same as the recovery-code reset path."""
    try:
        user = db.query(User).filter(User.id == 1).first()
        if not user or not user.reset_code_hash or not user.reset_code_expires_at:
            raise HTTPException(status_code=400, detail="No email reset code is pending for this account")
        if datetime.utcnow() > user.reset_code_expires_at:
            raise HTTPException(status_code=400, detail="This reset code has expired")
        if not verify_password(body.code.strip(), user.reset_code_hash):
            raise HTTPException(status_code=401, detail="Invalid reset code")
        if len(body.new_password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
            )
        user.password_hash = hash_password(body.new_password)
        user.reset_code_hash = None
        user.reset_code_expires_at = None
        new_recovery_code = generate_recovery_code()
        user.recovery_code_hash = hash_password(normalize_recovery_code(new_recovery_code))
        db.commit()
        return AuthResult(
            token=create_session_token(user.id),
            username=user.username,
            recovery_code=new_recovery_code,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e)


class MeResult(BaseModel):
    username: str
    name: str
    local_only: bool = False


@router.get("/auth/me", response_model=MeResult, dependencies=[Depends(require_auth)])
async def me(db: Session = Depends(get_db)):
    """Return the current user; 401 (via require_auth) if the token is invalid."""
    try:
        user = db.query(User).filter(User.id == 1).first()
        local_only = _is_local_only(user)
        # A session token must not outlive the account it names: if the install
        # is still on the first-run screen (no password and no no-account
        # choice), reject the stale token so the client falls back to setup.
        if not user or (not user.password_hash and not local_only):
            raise HTTPException(status_code=401, detail="Not authenticated")
        username = user.username or "user"
        # No-account mode has nothing to greet with unless a display name was
        # stored. Password accounts fall back to the username.
        if local_only:
            name = user.display_name or ""
        else:
            name = user.display_name or username
        return MeResult(username=username, name=name, local_only=local_only)
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e)
