"""
Unauthenticated auth + setup endpoints (mounted WITHOUT require_auth):
  - GET  /api/setup/status         — first-run detection + Plaid env-var presence
  - POST /api/auth/register        — claim the single-user account (first run only)
  - POST /api/auth/login           — password login
  - POST /api/auth/reset-password  — reset via one-time recovery code
  - GET  /api/auth/me              — validate the current session token

Single-user model: registration and login both operate on the user id=1 row.
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import (
    create_session_token,
    generate_recovery_code,
    hash_password,
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
    plaid_env: str
    plaid_ok: bool
    missing_plaid_vars: list[str]


@router.get("/setup/status", response_model=SetupStatus)
async def setup_status(db: Session = Depends(get_db)):
    """First-run + Plaid-config check for the login/loading screen."""
    try:
        user = db.query(User).filter(User.id == 1).first()
        missing = _missing_plaid_vars()
        return SetupStatus(
            account_exists=bool(user and user.password_hash),
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


class AuthResult(BaseModel):
    token: str
    username: str
    # Only populated on register and reset-password — the ONE time the plaintext
    # code is available. Never returned by /auth/login or /auth/me.
    recovery_code: str | None = None


@router.post("/auth/register", response_model=AuthResult)
async def register(body: RegisterBody, db: Session = Depends(get_db)):
    """Create the single-user account (first run only). Issues a one-time
    recovery code — the only path to reset a forgotten password without
    wiping local app data (no email transport for a single-user local app)."""
    try:
        user = _get_user(db)
        if user.password_hash:
            raise HTTPException(status_code=409, detail="An account already exists")
        username = body.username.strip()
        if not username:
            raise HTTPException(status_code=400, detail="Username is required")
        if len(body.password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
            )
        user.username = username
        user.display_name = (body.name or "").strip() or None
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


class ResetPasswordBody(BaseModel):
    recovery_code: str
    new_password: str


@router.post("/auth/reset-password", response_model=AuthResult)
async def reset_password(body: ResetPasswordBody, db: Session = Depends(get_db)):
    """Reset the password using the one-time recovery code, and issue a fresh
    code (the consumed one no longer works). This is the only "forgot
    password" path — there's no email transport to rely on for a single-user
    local app; the alternative is wiping the local app-data dir."""
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


class MeResult(BaseModel):
    username: str
    name: str


@router.get("/auth/me", response_model=MeResult, dependencies=[Depends(require_auth)])
async def me(db: Session = Depends(get_db)):
    """Return the current user; 401 (via require_auth) if the token is invalid."""
    try:
        user = db.query(User).filter(User.id == 1).first()
        # A session token must not outlive the account it names: if the account
        # has been reset to setup mode (no password), reject the stale token so
        # the client falls back to the login/setup screen.
        if not user or not user.password_hash:
            raise HTTPException(status_code=401, detail="Not authenticated")
        username = user.username if user else "user"
        # display_name falls back to username so the UI always has something.
        name = (user.display_name if user and user.display_name else username)
        return MeResult(username=username, name=name)
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e)
