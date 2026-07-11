"""
Transactional email transport via Resend (https://resend.com).

Deliberately not SMTP: we store a *send-only* Resend API key rather than a
mailbox password, so a leaked credential can only send mail through Resend
(revocable in their dashboard) — it can't read an inbox or touch a Google
account. Matches the app's raw-`requests` style (no SDK dependency).

Opt-in: send_email() no-ops (returns False) unless RESEND_API_KEY is set.

BYOK: settings are resolved via app_config (desktop, encrypted at rest) first,
os.getenv fallback second — mirrors PlaidService._setting so a packaged
desktop build (no env vars available) can configure Resend from Settings.

A second, fully independent Resend key (RESET_EMERGENCY_RESEND_API_KEY)
exists for password-reset emails only — see get_emergency_resend_api_key()/
send_password_reset_email(). Like the weekly-digest key, it's resolved via
app_config (BYOK, encrypted at rest) first and os.getenv second — but it is
never shared with, or substitutable for, RESEND_API_KEY: each is set and
read independently, so one can never silently stand in for the other.
send_email() accepts an optional api_key override to support this.
"""

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger("ledger")

RESEND_ENDPOINT = "https://api.resend.com/emails"
REQUEST_TIMEOUT_SECONDS = 10
# Resend's shared onboarding sender works without domain verification, handy
# for first-run/testing. Set WEEKLY_EMAIL_FROM to your verified domain later.
DEFAULT_FROM = "Ledger <onboarding@resend.dev>"


def _setting(name: str) -> Optional[str]:
    """Resolve an email-transport setting: app_config table first, os.getenv
    fallback. Never logs the resolved value."""
    try:
        from app.database import SessionLocal
        from app import app_config
        db = SessionLocal()
        try:
            val = app_config.get(db, name)
        finally:
            db.close()
        if val:
            return val
    except Exception:
        logger.debug("app_config lookup failed for %s; falling back to env", name, exc_info=True)
    return os.getenv(name)


def get_resend_api_key() -> str:
    """Effective Resend API key (app_config, else env), stripped. Never logged."""
    return (_setting("RESEND_API_KEY") or "").strip()


def get_from_address() -> Optional[str]:
    """Effective From address (app_config, else env), or None if unset."""
    from_addr = (_setting("WEEKLY_EMAIL_FROM") or "").strip()
    return from_addr or None


def is_configured() -> bool:
    """True if a Resend API key is available from either source."""
    return bool(get_resend_api_key())


def get_emergency_resend_api_key() -> str:
    """Effective emergency Resend API key for password-reset emails ONLY
    (app_config BYOK, else env), stripped. Resolved via its own app_config
    key (RESET_EMERGENCY_RESEND_API_KEY) — never reads or falls back to
    RESEND_API_KEY, so the two can never silently substitute for each other."""
    return (_setting("RESET_EMERGENCY_RESEND_API_KEY") or "").strip()


def is_reset_email_configured() -> bool:
    """True if the emergency key (password-reset transport) is set."""
    return bool(get_emergency_resend_api_key())


def send_email(to: str, subject: str, html: str, api_key: Optional[str] = None) -> bool:
    """
    Send one HTML email via Resend. Returns True on success, False if the
    transport is unconfigured or the request fails (never raises, so a mail
    failure can't break a scheduler cycle).

    api_key overrides the resolved weekly-digest key — used by
    send_password_reset_email() to route through the emergency key instead.
    Callers outside this module should not pass api_key directly; use
    send_password_reset_email() for reset emails.
    """
    effective_key = api_key if api_key is not None else get_resend_api_key()
    if not effective_key:
        logger.debug("send_email skipped: no Resend API key available")
        return False

    sender = get_from_address() or DEFAULT_FROM

    try:
        resp = requests.post(
            RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {effective_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": sender,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException:
        # Don't log the API key or full request; just the failure.
        logger.exception("Resend email delivery failed")
        return False


def send_password_reset_email(to: str, subject: str, html: str) -> bool:
    """Send a password-reset email through the emergency key ONLY — never
    the weekly-digest RESEND_API_KEY. Returns False (no-op) if
    RESET_EMERGENCY_RESEND_API_KEY isn't set."""
    key = get_emergency_resend_api_key()
    if not key:
        logger.debug("send_password_reset_email skipped: RESET_EMERGENCY_RESEND_API_KEY not set")
        return False
    return send_email(to, subject, html, api_key=key)
