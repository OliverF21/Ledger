"""Typed accessor for the app_config key/value table (desktop BYOK).

Secrets are Fernet-encrypted at rest via app.security. PlaidService reads
these values with an os.getenv fallback (see plaid_service.py).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import AppConfig
from app.security import encrypt_token, decrypt_token

# Canonical keys
PLAID_CLIENT_ID = "PLAID_CLIENT_ID"
PLAID_SECRET = "PLAID_SECRET"
PLAID_ENV = "PLAID_ENV"
PLAID_REDIRECT_URI = "PLAID_REDIRECT_URI"
WIZARD_DONE = "wizard_done"
SYNC_FREQUENCY_HOURS = "SYNC_FREQUENCY_HOURS"
RESEND_API_KEY = "RESEND_API_KEY"
WEEKLY_EMAIL_FROM = "WEEKLY_EMAIL_FROM"
# Separate BYOK key for password-reset emails only — never shared with, or
# substitutable for, RESEND_API_KEY (the weekly-digest transport). See
# app/email_sender.py.
RESET_EMERGENCY_RESEND_API_KEY = "RESET_EMERGENCY_RESEND_API_KEY"
PROPOSAL_SERVICE_KEY = "PROPOSAL_SERVICE_KEY"
ALCHEMY_API_KEY = "ALCHEMY_API_KEY"

# Allowed values for SYNC_FREQUENCY_HOURS: 0 means manual (no auto-sync).
SYNC_FREQUENCY_CHOICES = (0, 1, 6, 12, 24)
DEFAULT_SYNC_FREQUENCY_HOURS = 6


def get_sync_frequency_hours(db: Session) -> int:
    raw = get(db, SYNC_FREQUENCY_HOURS)
    if raw is None:
        return DEFAULT_SYNC_FREQUENCY_HOURS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SYNC_FREQUENCY_HOURS
    return value if value in SYNC_FREQUENCY_CHOICES else DEFAULT_SYNC_FREQUENCY_HOURS


def get(db: Session, key: str) -> Optional[str]:
    row = db.query(AppConfig).filter(AppConfig.key == key).first()
    if row is None or row.value is None:
        return None
    return decrypt_token(row.value) if row.is_secret else row.value


def set(db: Session, key: str, value: Optional[str], *, secret: bool = False) -> None:
    stored = encrypt_token(value) if (secret and value is not None) else value
    row = db.query(AppConfig).filter(AppConfig.key == key).first()
    if row is None:
        row = AppConfig(key=key, value=stored, is_secret=secret)
        db.add(row)
    else:
        row.value = stored
        row.is_secret = secret
    db.commit()


def delete(db: Session, key: str) -> None:
    db.query(AppConfig).filter(AppConfig.key == key).delete()
    db.commit()


def get_plaid_config(db: Session) -> dict:
    return {
        "client_id": get(db, PLAID_CLIENT_ID),
        "secret": get(db, PLAID_SECRET),
        "env": get(db, PLAID_ENV),
        "redirect_uri": get(db, PLAID_REDIRECT_URI),
    }
