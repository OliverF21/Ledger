"""
Alert preference endpoints.
- GET /settings/alerts: current alert preferences
- PUT /settings/alerts: update alert preferences
- GET /settings/alerts/active: currently-active alerts (budget exceeded, large transactions)
"""

import json
import os
import secrets
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet

# Aliased: the GET /alerts route below is also named get_alert_prefs and
# would otherwise shadow this import at module level.
from app.alerts import compute_active_alerts, get_alert_prefs as resolve_alert_prefs
from app.auth import (
    _proposal_service_key,
    generate_recovery_code,
    hash_password,
    is_valid_email,
    mask_email,
    normalize_recovery_code,
)
from app.budgets_db import get_budgets_db
from app.database import get_db
from app.errors import log_and_raise
from app.models import User
from app import app_config, email_sender, paths
from app.plaid_service import PlaidService

router = APIRouter(prefix="/settings", tags=["settings"])


class AlertPrefs(BaseModel):
    budget_exceeded_enabled: bool
    large_txn_enabled: bool
    large_txn_threshold: float


def _get_user(db: Session) -> User:
    return db.query(User).filter(User.id == 1).first()


def _prefs_from_user(user: User) -> AlertPrefs:
    prefs = resolve_alert_prefs(user)
    return AlertPrefs(
        budget_exceeded_enabled=prefs.budget_exceeded_enabled,
        large_txn_enabled=prefs.large_txn_enabled,
        large_txn_threshold=prefs.large_txn_threshold,
    )


@router.get("/alerts", response_model=AlertPrefs)
async def get_alert_prefs(db: Session = Depends(get_db)):
    """Current alert preferences, with documented defaults for unset (NULL) values."""
    try:
        return _prefs_from_user(_get_user(db))
    except Exception as e:
        log_and_raise(e)


class UpdateAlertPrefsRequest(BaseModel):
    budget_exceeded_enabled: Optional[bool] = None
    large_txn_enabled: Optional[bool] = None
    large_txn_threshold: Optional[float] = None


@router.put("/alerts", response_model=AlertPrefs)
async def update_alert_prefs(req: UpdateAlertPrefsRequest, db: Session = Depends(get_db)):
    """Partial update of alert preferences - only provided fields are changed."""
    try:
        user = _get_user(db)
        if req.budget_exceeded_enabled is not None:
            user.alert_budget_exceeded_enabled = req.budget_exceeded_enabled
        if req.large_txn_enabled is not None:
            user.alert_large_txn_enabled = req.large_txn_enabled
        if req.large_txn_threshold is not None:
            user.alert_large_txn_threshold = req.large_txn_threshold
        db.commit()
        return _prefs_from_user(user)
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


class BudgetExceededAlert(BaseModel):
    category: str
    spent: float
    limit: float


class LargeTransactionAlert(BaseModel):
    id: int
    merchant: str
    amount: float
    date: str


class ActiveAlertsResponse(BaseModel):
    budget_exceeded: list[BudgetExceededAlert]
    large_transactions: list[LargeTransactionAlert]


# ── Weekly summary email ─────────────────────────────────────────────────────

class WeeklyEmailPrefs(BaseModel):
    enabled: bool
    email: Optional[str] = None
    # Whether a Resend API key is available (app_config BYOK, else env). The
    # toggle can be flipped on without it, but no email will actually send
    # until it is. Kept alongside has_resend_key for frontend compatibility.
    transport_configured: bool
    has_resend_key: bool
    from_address: Optional[str] = None


def _weekly_email_prefs(user: User) -> WeeklyEmailPrefs:
    has_key = email_sender.is_configured()
    return WeeklyEmailPrefs(
        enabled=bool(user.weekly_email_enabled),
        email=user.weekly_email_to,
        transport_configured=has_key,
        has_resend_key=has_key,
        from_address=email_sender.get_from_address(),
    )


@router.get("/weekly-email", response_model=WeeklyEmailPrefs)
async def get_weekly_email_prefs(db: Session = Depends(get_db)):
    try:
        return _weekly_email_prefs(_get_user(db))
    except Exception as e:
        log_and_raise(e)


class UpdateWeeklyEmailRequest(BaseModel):
    enabled: Optional[bool] = None
    email: Optional[str] = None
    # BYOK transport config (desktop). Blank/omitted resend_api_key keeps the
    # stored key (same convention as PlaidConfigUpdate.secret).
    resend_api_key: Optional[str] = None
    from_address: Optional[str] = None


@router.put("/weekly-email", response_model=WeeklyEmailPrefs)
async def update_weekly_email_prefs(req: UpdateWeeklyEmailRequest, db: Session = Depends(get_db)):
    """Partial update. Enabling without a stored (or provided) email is rejected."""
    try:
        user = _get_user(db)
        if req.email is not None:
            email = req.email.strip()
            user.weekly_email_to = email or None
        if req.enabled is not None:
            if req.enabled and not (user.weekly_email_to or "").strip():
                raise HTTPException(status_code=400, detail="Add a recipient email before enabling")
            user.weekly_email_enabled = req.enabled
        if req.resend_api_key:  # only overwrite when a non-empty key is provided
            app_config.set(db, app_config.RESEND_API_KEY, req.resend_api_key.strip(), secret=True)
        if req.from_address is not None:
            app_config.set(db, app_config.WEEKLY_EMAIL_FROM, req.from_address.strip() or None)
        db.commit()
        return _weekly_email_prefs(user)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


@router.get("/alerts/active", response_model=ActiveAlertsResponse)
async def get_active_alerts(
    db: Session = Depends(get_db),
    bdb: Session = Depends(get_budgets_db),
):
    """
    Currently-active alerts, respecting each toggle's enabled state (empty
    list if disabled). No dismiss/acknowledge tracking - a budget-exceeded
    alert clears itself once spending or the limit changes, and a large
    transaction ages out of the trailing window on its own.
    """
    try:
        budget_exceeded, large_transactions = compute_active_alerts(db, bdb)
        return ActiveAlertsResponse(
            budget_exceeded=[
                BudgetExceededAlert(category=b.category, spent=b.spent, limit=b.limit)
                for b in budget_exceeded
            ],
            large_transactions=[
                LargeTransactionAlert(id=t.id, merchant=t.merchant, amount=t.amount, date=t.date)
                for t in large_transactions
            ],
        )
    except Exception as e:
        log_and_raise(e)


# ── Plaid BYOK config (desktop) ──────────────────────────────────────────────

class PlaidConfigResponse(BaseModel):
    client_id: Optional[str] = None
    env: str = "sandbox"
    redirect_uri: Optional[str] = None
    has_secret: bool = False
    configured: bool = False
    wizard_done: bool = False


class PlaidConfigUpdate(BaseModel):
    client_id: Optional[str] = None
    env: Optional[str] = None
    secret: Optional[str] = None
    redirect_uri: Optional[str] = None


class PlaidConfigTest(BaseModel):
    client_id: Optional[str] = None
    env: Optional[str] = None
    secret: Optional[str] = None


def _plaid_config_response(db: Session) -> PlaidConfigResponse:
    cfg = app_config.get_plaid_config(db)
    return PlaidConfigResponse(
        client_id=cfg["client_id"],
        # Effective env (app_config → PLAID_ENV env var), so the UI reflects the
        # real environment instead of defaulting to "sandbox" for a user whose
        # creds live only in .env.
        env=(PlaidService._setting("PLAID_ENV") or "sandbox"),
        redirect_uri=cfg["redirect_uri"],
        has_secret=bool(cfg["secret"]),
        # Mirrors the resolution used by the 409 guard on Plaid endpoints
        # (app_config table, falling back to PLAID_CLIENT_ID/PLAID_*_SECRET
        # env vars) so a dev user with creds only in .env isn't
        # incorrectly dropped into the first-run setup wizard.
        configured=PlaidService.is_configured(),
        wizard_done=(app_config.get(db, app_config.WIZARD_DONE) == "1"),
    )


@router.get("/plaid-config", response_model=PlaidConfigResponse)
async def get_plaid_config(db: Session = Depends(get_db)):
    try:
        return _plaid_config_response(db)
    except Exception as e:
        log_and_raise(e)


@router.put("/plaid-config", response_model=PlaidConfigResponse)
async def update_plaid_config(req: PlaidConfigUpdate, db: Session = Depends(get_db)):
    """Persist Plaid creds. `secret` omitted/blank keeps the stored one."""
    try:
        if req.client_id is not None:
            app_config.set(db, app_config.PLAID_CLIENT_ID, req.client_id.strip())
        if req.env is not None:
            app_config.set(db, app_config.PLAID_ENV, req.env.strip().lower())
        if req.redirect_uri is not None:
            app_config.set(db, app_config.PLAID_REDIRECT_URI, req.redirect_uri.strip() or None)
        if req.secret:  # only overwrite when a non-empty secret is provided
            app_config.set(db, app_config.PLAID_SECRET, req.secret, secret=True)
        return _plaid_config_response(db)
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


@router.post("/plaid-config/test")
async def test_plaid_config(req: PlaidConfigTest, db: Session = Depends(get_db)):
    """Validate creds by creating a throwaway Plaid link token. Persists
    provided values first so create_link_token/_setting picks them up. Never
    echoes the secret."""
    try:
        if req.client_id is not None:
            app_config.set(db, app_config.PLAID_CLIENT_ID, req.client_id.strip())
        if req.env is not None:
            app_config.set(db, app_config.PLAID_ENV, req.env.strip().lower())
        if req.secret:
            app_config.set(db, app_config.PLAID_SECRET, req.secret, secret=True)

        if not PlaidService.is_configured():
            return {"ok": False, "message": "Enter a client ID and secret first."}

        try:
            PlaidService.create_link_token(user_id=1)
        except Exception as e:  # noqa: BLE001
            raw = str(e).upper()
            if "INVALID_API_KEYS" in raw or "INVALID_CLIENT" in raw or "UNAUTHORIZED" in raw:
                msg = "Invalid client ID or secret for this environment."
            elif "PRODUCTS" in raw or "NOT_ENABLED" in raw or "INVALID_PRODUCT" in raw:
                msg = "Keys are valid but a required product isn't enabled in your Plaid dashboard."
            else:
                msg = "Could not reach Plaid with these credentials. Check the environment (sandbox/production)."
            return {"ok": False, "message": msg}

        return {"ok": True, "message": "Connection successful."}
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


# ── AI Advisor (MCP) guided setup ────────────────────────────────────────────
# Bundled desktop backend's fixed loopback port (see backend/desktop_main.py).
# Used only to pre-fill the LEDGER_API_URL in the pasteable Claude Desktop
# config snippet below — the MCP server itself talks to whichever backend the
# user points it at via that env var.
_DESKTOP_BACKEND_URL = "http://127.0.0.1:17384"


class AdvisorConfigResponse(BaseModel):
    configured: bool = False
    service_key: Optional[str] = None
    config_snippet: str = ""


def _advisor_config_snippet(service_key: str) -> str:
    """Ready-to-paste claude_desktop_config.json MCP server block, matching
    the format documented in backend/MCP_SETUP.md, with the real key and the
    desktop backend's loopback URL substituted in."""
    snippet = {
        "mcpServers": {
            "ledger-analytics": {
                "command": "python",
                "args": ["-m", "mcp_server.server"],
                "cwd": "/path/to/ledger/backend",
                "env": {
                    "PROPOSAL_SERVICE_KEY": service_key,
                    "LEDGER_API_URL": _DESKTOP_BACKEND_URL,
                },
            }
        }
    }
    return json.dumps(snippet, indent=2)


def _advisor_config_response(db: Session) -> AdvisorConfigResponse:
    # Mirrors require_proposal_service's resolution (app_config, then env) so
    # "configured" reflects whether propose_budget would actually work.
    key = _proposal_service_key()
    if not key:
        return AdvisorConfigResponse(configured=False, service_key=None, config_snippet="")
    return AdvisorConfigResponse(
        configured=True,
        service_key=key,
        config_snippet=_advisor_config_snippet(key),
    )


@router.get("/advisor-config", response_model=AdvisorConfigResponse)
async def get_advisor_config(db: Session = Depends(get_db)):
    try:
        return _advisor_config_response(db)
    except Exception as e:
        log_and_raise(e)


@router.post("/advisor-config/generate", response_model=AdvisorConfigResponse)
async def generate_advisor_config(db: Session = Depends(get_db)):
    """Generate and persist a fresh PROPOSAL_SERVICE_KEY. Unlike the Plaid
    secret, this key is deliberately echoed back (GET included) — the user
    needs to copy it into their Claude Desktop config."""
    try:
        key = secrets.token_urlsafe(32)
        app_config.set(db, app_config.PROPOSAL_SERVICE_KEY, key, secret=True)
        return _advisor_config_response(db)
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


# ── Sync frequency ───────────────────────────────────────────────────────────

class SyncConfigResponse(BaseModel):
    frequency_hours: int


class SyncConfigUpdate(BaseModel):
    frequency_hours: int


@router.get("/sync-config", response_model=SyncConfigResponse)
async def get_sync_config(db: Session = Depends(get_db)):
    try:
        return SyncConfigResponse(frequency_hours=app_config.get_sync_frequency_hours(db))
    except Exception as e:
        log_and_raise(e)


@router.put("/sync-config", response_model=SyncConfigResponse)
async def update_sync_config(req: SyncConfigUpdate, db: Session = Depends(get_db)):
    """Persist the sync frequency (0 = manual/no auto-sync) and reschedule
    the background job so the change takes effect without a restart."""
    try:
        if req.frequency_hours not in app_config.SYNC_FREQUENCY_CHOICES:
            raise HTTPException(
                status_code=400,
                detail=f"frequency_hours must be one of {sorted(app_config.SYNC_FREQUENCY_CHOICES)}",
            )
        app_config.set(db, app_config.SYNC_FREQUENCY_HOURS, str(req.frequency_hours))

        from app.scheduler import reschedule_sync
        reschedule_sync(req.frequency_hours)

        return SyncConfigResponse(frequency_hours=req.frequency_hours)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


@router.put("/wizard-done")
async def mark_wizard_done(db: Session = Depends(get_db)):
    try:
        app_config.set(db, app_config.WIZARD_DONE, "1")
        return {"wizard_done": True}
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


# ── Import existing Ledger data (desktop upgrade path) ──────────────────────

class ImportRequest(BaseModel):
    source_dir: str
    confirm_overwrite: bool = False


def _read_env_file(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _safe_child(source_dir: Path, name: str) -> Path:
    """Resolve name within source_dir, rejecting symlink/traversal escapes."""
    base = source_dir.resolve(strict=True)
    p = (base / name)
    real = p.resolve()
    if not str(real).startswith(str(base) + os.sep) and real != base / name:
        raise HTTPException(status_code=400, detail=f"Unsafe path for {name}")
    if p.is_symlink():
        raise HTTPException(status_code=400, detail=f"Refusing to follow symlink: {name}")
    return p


def _do_import(source_dir: str, *, confirm_overwrite: bool) -> dict:
    src = Path(source_dir)
    if not src.exists():
        raise HTTPException(status_code=400, detail="Source folder not found")
    ledger_src = _safe_child(src, "ledger.db")
    if not ledger_src.exists():
        raise HTTPException(status_code=400, detail="No ledger.db in the selected folder")

    env = _read_env_file(_safe_child(src, ".env"))
    src_key = env.get("ENCRYPTION_KEY")
    if not src_key:
        raise HTTPException(status_code=400, detail="Source .env has no ENCRYPTION_KEY")

    # Validate the key actually decrypts a token from the source DB.
    con = sqlite3.connect(str(ledger_src))
    try:
        rows = con.execute("SELECT access_token_encrypted FROM items").fetchall()
    finally:
        con.close()
    fernet = Fernet(src_key.encode())
    non_null_tokens = [tok for (tok,) in rows if tok]
    if non_null_tokens:
        try:
            fernet.decrypt(non_null_tokens[0].encode())  # raises on wrong key
        except Exception:
            raise HTTPException(status_code=400, detail="Encryption key does not match the source data")
    # else: zero linked items in the source DB means there is nothing to
    # validate the key against. This is a deliberate decision (not an
    # oversight) to allow importing from a fresh/never-linked install.
    imported_items = len(rows)

    # Guard against clobbering a target that already has real user data.
    # Note: startup's create_all() always creates the schema, so checking
    # for table existence would false-positive on every prior run. Instead
    # check for actual rows in the tables that matter.
    target_ledger = paths.ledger_db_path()
    if target_ledger.exists() and target_ledger.stat().st_size > 0 and not confirm_overwrite:
        con = sqlite3.connect(str(target_ledger))
        try:
            populated = False
            for table in ("items", "transactions"):
                try:
                    count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except sqlite3.OperationalError:
                    continue  # table doesn't exist yet
                if count > 0:
                    populated = True
                    break
        finally:
            con.close()
        if populated:
            raise HTTPException(status_code=409, detail="Target already has data; confirm overwrite")

    # Back up existing target DBs before overwriting.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for tgt in (paths.ledger_db_path(), paths.budgets_db_path()):
        if tgt.exists():
            shutil.copy2(tgt, tgt.with_suffix(tgt.suffix + f".bak-{stamp}"))

    # Copy DBs.
    shutil.copy2(ledger_src, paths.ledger_db_path())
    budgets_src = _safe_child(src, "budgets.db")
    if budgets_src.exists():
        shutil.copy2(budgets_src, paths.budgets_db_path())

    # Write imported key to config.json (0600).
    import json
    cfg_path = paths.config_path()
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            cfg = {}
    cfg["ENCRYPTION_KEY"] = src_key
    cfg_path.write_text(json.dumps(cfg, indent=2))
    if os.name == "posix":
        try:
            cfg_path.chmod(0o600)
        except OSError:
            pass

    # Migrate .env Plaid creds into the imported ledger.db's app_config table,
    # encrypting the secret with the imported key.
    imported_env = (env.get("PLAID_ENV") or "sandbox").lower()
    secret = env.get("PLAID_PROD_SECRET") if imported_env == "production" else env.get("PLAID_SANDBOX_SECRET")
    con = sqlite3.connect(str(paths.ledger_db_path()))
    try:
        con.execute("CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT, is_secret BOOLEAN NOT NULL DEFAULT 0)")
        def _put(k, v, is_secret=False):
            if v is None:
                return
            stored = Fernet(src_key.encode()).encrypt(v.encode()).decode() if is_secret else v
            con.execute("INSERT OR REPLACE INTO app_config (key, value, is_secret) VALUES (?,?,?)",
                        (k, stored, 1 if is_secret else 0))
        _put("PLAID_CLIENT_ID", env.get("PLAID_CLIENT_ID"))
        _put("PLAID_ENV", imported_env)
        _put("PLAID_SECRET", secret, is_secret=True)
        con.commit()
    finally:
        con.close()

    return {"imported_items": imported_items, "restart_required": True}


@router.post("/import")
async def import_existing_data(req: ImportRequest):
    try:
        return _do_import(req.source_dir, confirm_overwrite=req.confirm_overwrite)
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e, status_code=400)


# ── Recovery code (account security) ─────────────────────────────────────────

class RecoveryCodeStatus(BaseModel):
    configured: bool


@router.get("/security/recovery-code", response_model=RecoveryCodeStatus)
async def get_recovery_code_status(db: Session = Depends(get_db)):
    """Whether a recovery code is set — never returns the code itself (it's
    only shown once, at generation time, from the POST endpoint below)."""
    try:
        user = _get_user(db)
        return RecoveryCodeStatus(configured=bool(user.recovery_code_hash))
    except Exception as e:
        log_and_raise(e)


class RecoveryCodeResponse(BaseModel):
    recovery_code: str


@router.post("/security/recovery-code", response_model=RecoveryCodeResponse)
async def generate_new_recovery_code(db: Session = Depends(get_db)):
    """Generate (or rotate) the recovery code for accounts created before this
    feature existed, or after a user wants a fresh one. Shown exactly once."""
    try:
        user = _get_user(db)
        code = generate_recovery_code()
        user.recovery_code_hash = hash_password(normalize_recovery_code(code))
        db.commit()
        return RecoveryCodeResponse(recovery_code=code)
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


class RecoveryEmailStatus(BaseModel):
    email: str | None = None


@router.get("/security/email", response_model=RecoveryEmailStatus)
async def get_recovery_email(db: Session = Depends(get_db)):
    """Masked account recovery email (used by /api/auth/forgot-password),
    or null if unset."""
    try:
        user = _get_user(db)
        return RecoveryEmailStatus(email=mask_email(user.email) if user.email else None)
    except Exception as e:
        log_and_raise(e)


class RecoveryEmailUpdate(BaseModel):
    email: str


@router.put("/security/email", response_model=RecoveryEmailStatus)
async def put_recovery_email(body: RecoveryEmailUpdate, db: Session = Depends(get_db)):
    """Set or clear (blank) the account recovery email. A blank string is a
    deliberate "clear" signal, not a malformed address, so it skips
    validation; any non-blank value must look like a real email."""
    try:
        user = _get_user(db)
        email = body.email.strip()
        if email and not is_valid_email(email):
            raise HTTPException(status_code=400, detail="Invalid email address")
        user.email = email or None
        db.commit()
        return RecoveryEmailStatus(email=mask_email(user.email) if user.email else None)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)
