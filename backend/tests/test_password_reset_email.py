"""Email-based password reset: register(email), reset-options,
forgot-password, reset-password-email, and the Settings recovery-email
endpoints. Mirrors the fixture pattern in tests/test_weekly_email_config.py."""
from __future__ import annotations

import os
from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.pop("RESET_EMERGENCY_RESEND_API_KEY", None)
os.environ.pop("RESEND_API_KEY", None)

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.models import Base, User  # noqa: E402
from app import database  # noqa: E402


@pytest.fixture()
def memdb(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ledger.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "SessionLocal", TestSession)
    yield TestSession


@pytest.fixture()
def client(memdb, monkeypatch):
    import main
    from app.auth import require_auth

    main.app.dependency_overrides[require_auth] = lambda: 1

    def _get_db():
        s = memdb()
        try:
            yield s
        finally:
            s.close()
    main.app.dependency_overrides[database.get_db] = _get_db
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


# ── Register with optional email ─────────────────────────────────────────────

def test_register_without_email_succeeds(client):
    r = client.post("/api/auth/register", json={"username": "alice", "password": "hunter2222"})
    assert r.status_code == 200
    assert r.json()["recovery_code"]


def test_register_with_email_stores_it(client, memdb):
    r = client.post("/api/auth/register", json={
        "username": "alice", "password": "hunter2222", "email": "alice@example.com",
    })
    assert r.status_code == 200
    s = memdb()
    user = s.query(User).filter(User.id == 1).first()
    assert user.email == "alice@example.com"
    s.close()


def test_register_with_malformed_email_rejected(client):
    r = client.post("/api/auth/register", json={
        "username": "alice", "password": "hunter2222", "email": "not-an-email",
    })
    assert r.status_code == 400


# ── reset-options ─────────────────────────────────────────────────────────

def test_reset_options_unavailable_with_no_email_no_key(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "hunter2222"})
    r = client.get("/api/auth/reset-options")
    assert r.status_code == 200
    assert r.json() == {"email_available": False, "masked_email": None}


def test_reset_options_unavailable_with_email_but_no_key(client):
    client.post("/api/auth/register", json={
        "username": "alice", "password": "hunter2222", "email": "alice@example.com",
    })
    r = client.get("/api/auth/reset-options")
    assert r.json()["email_available"] is False


def test_reset_options_available_with_email_and_key(client, monkeypatch):
    monkeypatch.setenv("RESET_EMERGENCY_RESEND_API_KEY", "emergency_secret")
    client.post("/api/auth/register", json={
        "username": "alice", "password": "hunter2222", "email": "alice@example.com",
    })
    r = client.get("/api/auth/reset-options")
    body = r.json()
    assert body["email_available"] is True
    assert body["masked_email"] == "a***@example.com"


# ── forgot-password ─────────────────────────────────────────────────────────

def test_forgot_password_400_when_unavailable(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "hunter2222"})
    r = client.post("/api/auth/forgot-password")
    assert r.status_code == 400


def test_forgot_password_sends_email_and_sets_code(client, monkeypatch, memdb):
    monkeypatch.setenv("RESET_EMERGENCY_RESEND_API_KEY", "emergency_secret")
    client.post("/api/auth/register", json={
        "username": "alice", "password": "hunter2222", "email": "alice@example.com",
    })

    from app import email_sender
    captured = {}

    def fake_send(to, subject, html):
        captured["to"] = to
        captured["html"] = html
        return True

    monkeypatch.setattr(email_sender, "send_password_reset_email", fake_send)

    r = client.post("/api/auth/forgot-password")
    assert r.status_code == 200
    assert r.json() == {"sent": True}
    assert captured["to"] == "alice@example.com"

    s = memdb()
    user = s.query(User).filter(User.id == 1).first()
    assert user.reset_code_hash is not None
    assert user.reset_code_expires_at is not None
    s.close()


def test_forgot_password_502_when_send_fails(client, monkeypatch):
    monkeypatch.setenv("RESET_EMERGENCY_RESEND_API_KEY", "emergency_secret")
    client.post("/api/auth/register", json={
        "username": "alice", "password": "hunter2222", "email": "alice@example.com",
    })
    from app import email_sender
    monkeypatch.setattr(email_sender, "send_password_reset_email", lambda to, subject, html: False)
    r = client.post("/api/auth/forgot-password")
    assert r.status_code == 502


# ── reset-password-email ─────────────────────────────────────────────────────

def _request_code(client, monkeypatch, memdb):
    monkeypatch.setenv("RESET_EMERGENCY_RESEND_API_KEY", "emergency_secret")
    client.post("/api/auth/register", json={
        "username": "alice", "password": "old_password_1", "email": "alice@example.com",
    })
    captured = {}
    from app import email_sender
    def fake_send(to, subject, html):
        # Pull the 6-digit code out of the HTML body.
        import re
        captured["code"] = re.search(r"<strong>(\d{6})</strong>", html).group(1)
        return True
    monkeypatch.setattr(email_sender, "send_password_reset_email", fake_send)
    client.post("/api/auth/forgot-password")
    return captured["code"]


def test_reset_password_email_success_rotates_recovery_code_and_logs_in(client, monkeypatch, memdb):
    code = _request_code(client, monkeypatch, memdb)

    old_login = client.post("/api/auth/login", json={"username": "alice", "password": "old_password_1"})
    assert old_login.status_code == 200

    r = client.post("/api/auth/reset-password-email", json={"code": code, "new_password": "new_password_1"})
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["recovery_code"]

    assert client.post("/api/auth/login", json={"username": "alice", "password": "old_password_1"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "alice", "password": "new_password_1"}).status_code == 200

    s = memdb()
    user = s.query(User).filter(User.id == 1).first()
    assert user.reset_code_hash is None
    assert user.reset_code_expires_at is None
    s.close()


def test_reset_password_email_wrong_code_rejected(client, monkeypatch, memdb):
    _request_code(client, monkeypatch, memdb)
    r = client.post("/api/auth/reset-password-email", json={"code": "000000", "new_password": "new_password_1"})
    assert r.status_code == 401


def test_reset_password_email_expired_code_rejected(client, monkeypatch, memdb):
    code = _request_code(client, monkeypatch, memdb)
    s = memdb()
    from datetime import datetime, timedelta
    user = s.query(User).filter(User.id == 1).first()
    user.reset_code_expires_at = datetime.utcnow() - timedelta(minutes=1)
    s.commit()
    s.close()

    r = client.post("/api/auth/reset-password-email", json={"code": code, "new_password": "new_password_1"})
    assert r.status_code == 400


def test_reset_password_email_no_pending_code_rejected(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "old_password_1"})
    r = client.post("/api/auth/reset-password-email", json={"code": "123456", "new_password": "new_password_1"})
    assert r.status_code == 400


def test_reset_password_email_too_short_rejected(client, monkeypatch, memdb):
    code = _request_code(client, monkeypatch, memdb)
    r = client.post("/api/auth/reset-password-email", json={"code": code, "new_password": "short"})
    assert r.status_code == 400


def test_reset_password_email_code_with_whitespace_still_succeeds(client, monkeypatch, memdb):
    """Mirrors the forgiving UX of the recovery-code path (normalize_recovery_code):
    a code copy-pasted with surrounding whitespace should still verify."""
    code = _request_code(client, monkeypatch, memdb)
    r = client.post("/api/auth/reset-password-email", json={
        "code": f"  {code}\n", "new_password": "new_password_1",
    })
    assert r.status_code == 200
    assert client.post(
        "/api/auth/login", json={"username": "alice", "password": "new_password_1"}
    ).status_code == 200


# ── Settings: recovery email ─────────────────────────────────────────────────

def test_get_recovery_email_status_initially_none(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "hunter2222"})
    r = client.get("/api/settings/security/email")
    assert r.status_code == 200
    assert r.json() == {"email": None}


def test_put_recovery_email_then_get_shows_masked(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "hunter2222"})
    r = client.put("/api/settings/security/email", json={"email": "bob@example.com"})
    assert r.status_code == 200
    assert r.json() == {"email": "b***@example.com"}

    g = client.get("/api/settings/security/email")
    assert g.json() == {"email": "b***@example.com"}


def test_put_recovery_email_blank_clears_it(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "hunter2222"})
    client.put("/api/settings/security/email", json={"email": "bob@example.com"})
    r = client.put("/api/settings/security/email", json={"email": ""})
    assert r.status_code == 200
    assert r.json() == {"email": None}

    # Prove the clear persisted to the DB, not just reflected in the PUT response.
    g = client.get("/api/settings/security/email")
    assert g.status_code == 200
    assert g.json() == {"email": None}


def test_put_recovery_email_malformed_rejected(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "hunter2222"})
    r = client.put("/api/settings/security/email", json={"email": "not-an-email"})
    assert r.status_code == 400
