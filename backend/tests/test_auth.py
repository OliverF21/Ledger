"""Auth tests. Env must be set BEFORE importing app modules (security.py
raises at import if ENCRYPTION_KEY is missing)."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ["API_KEY"] = "test-legacy-key"
os.environ["SESSION_TTL_DAYS"] = "30"
os.environ.setdefault("PLAID_CLIENT_ID", "test_client_id")
os.environ.setdefault("PLAID_SANDBOX_SECRET", "test_sandbox_secret")

import pytest  # noqa: E402

from app import auth  # noqa: E402


# ── Password hashing ────────────────────────────────────────────────────────

def test_password_round_trip():
    stored = auth.hash_password("correct horse battery")
    assert auth.verify_password("correct horse battery", stored)
    assert not auth.verify_password("wrong password", stored)
    assert not auth.verify_password("anything", None)


def test_password_hash_is_salted():
    a = auth.hash_password("samepass1")
    b = auth.hash_password("samepass1")
    assert a != b  # random salt
    assert auth.verify_password("samepass1", a)
    assert auth.verify_password("samepass1", b)


# ── Session tokens ──────────────────────────────────────────────────────────

def test_token_round_trip():
    token = auth.create_session_token(1)
    assert auth.verify_session_token(token) == 1


def test_token_tampered_rejected():
    token = auth.create_session_token(1)
    assert auth.verify_session_token(token[:-2] + ("aa" if token[-2:] != "aa" else "bb")) is None
    assert auth.verify_session_token("not-a-token") is None
    assert auth.verify_session_token("") is None


def test_token_expired_rejected(monkeypatch):
    token = auth.create_session_token(1)
    # Force TTL to 0 so any already-issued token is treated as expired.
    monkeypatch.setattr(auth, "_SESSION_TTL_SECONDS", 0)
    import time
    time.sleep(1)
    assert auth.verify_session_token(token) is None


# ── require_auth matrix ─────────────────────────────────────────────────────

def _call_require(authorization=None, x_api_key=None):
    from fastapi import HTTPException
    try:
        auth.require_auth(authorization=authorization, x_api_key=x_api_key)
        return True
    except HTTPException:
        return False


def test_require_auth_bearer_ok():
    token = auth.create_session_token(1)
    assert _call_require(authorization=f"Bearer {token}")


def test_require_auth_api_key_ok():
    assert _call_require(x_api_key="test-legacy-key")


def test_require_auth_neither_401():
    assert not _call_require()
    assert not _call_require(authorization="Bearer garbage")
    assert not _call_require(x_api_key="wrong")


# ── Endpoints via TestClient ────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient backed by a throwaway SQLite DB so register/login don't
    touch the real ledger.db."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("BUDGETS_DATABASE_URL", f"sqlite:///{tmp_path / 'budgets.db'}")

    # Import inside the fixture so the patched DATABASE_URL is picked up.
    import importlib
    from app import database
    importlib.reload(database)
    from app.models import Base
    Base.metadata.create_all(bind=database.engine)

    import main
    importlib.reload(main)
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def test_setup_status_no_account(client):
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    data = r.json()
    assert data["account_exists"] is False
    assert data["plaid_ok"] is True
    assert data["missing_plaid_vars"] == []
    # Never leak values
    assert "test_sandbox_secret" not in r.text


def test_setup_status_missing_plaid_var(client, monkeypatch):
    monkeypatch.delenv("PLAID_SANDBOX_SECRET", raising=False)
    r = client.get("/api/setup/status")
    data = r.json()
    assert "PLAID_SANDBOX_SECRET" in data["missing_plaid_vars"]
    assert data["plaid_ok"] is False


def test_register_login_me_flow(client):
    # Register
    r = client.post("/api/auth/register", json={"username": "olive", "password": "hunter2hunter2"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert r.json()["username"] == "olive"

    # Second register → 409
    r2 = client.post("/api/auth/register", json={"username": "x", "password": "yyyyyyyy"})
    assert r2.status_code == 409

    # Wrong password → 401
    assert client.post("/api/auth/login", json={"username": "olive", "password": "nope"}).status_code == 401

    # Correct login
    r3 = client.post("/api/auth/login", json={"username": "olive", "password": "hunter2hunter2"})
    assert r3.status_code == 200

    # /me with issued token
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "olive"

    # /me without token → 401
    assert client.get("/api/auth/me").status_code == 401


def test_register_short_password_rejected(client):
    r = client.post("/api/auth/register", json={"username": "a", "password": "short"})
    assert r.status_code == 400


def test_protected_route_requires_auth(client):
    # No credentials → 401
    assert client.get("/api/plaid/accounts").status_code == 401
    # Legacy X-API-Key still works
    r = client.get("/api/plaid/accounts", headers={"X-API-Key": "test-legacy-key"})
    assert r.status_code == 200


# ── Recovery code / password reset ──────────────────────────────────────────

def test_register_returns_recovery_code(client):
    r = client.post("/api/auth/register", json={"username": "olive", "password": "hunter2hunter2"})
    assert r.status_code == 200
    code = r.json()["recovery_code"]
    assert code and len(code) == 14  # XXXX-XXXX-XXXX
    # Login never returns a recovery code.
    login = client.post("/api/auth/login", json={"username": "olive", "password": "hunter2hunter2"})
    assert login.json()["recovery_code"] is None


def test_reset_password_with_recovery_code(client):
    reg = client.post("/api/auth/register", json={"username": "olive", "password": "hunter2hunter2"})
    code = reg.json()["recovery_code"]

    # Wrong code rejected.
    bad = client.post("/api/auth/reset-password", json={"recovery_code": "AAAA-AAAA-AAAA", "new_password": "newpassword1"})
    assert bad.status_code == 401

    # Correct code resets the password and returns a NEW code + a working token.
    r = client.post("/api/auth/reset-password", json={"recovery_code": code, "new_password": "newpassword1"})
    assert r.status_code == 200
    new_code = r.json()["recovery_code"]
    assert new_code and new_code != code

    # Old password no longer works; new one does.
    assert client.post("/api/auth/login", json={"username": "olive", "password": "hunter2hunter2"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "olive", "password": "newpassword1"}).status_code == 200

    # The consumed code cannot be reused.
    reuse = client.post("/api/auth/reset-password", json={"recovery_code": code, "new_password": "another12345"})
    assert reuse.status_code == 401

    # The new code works for a subsequent reset.
    r2 = client.post("/api/auth/reset-password", json={"recovery_code": new_code, "new_password": "another12345"})
    assert r2.status_code == 200


def test_reset_password_accepts_code_without_dashes_or_case(client):
    reg = client.post("/api/auth/register", json={"username": "olive", "password": "hunter2hunter2"})
    code = reg.json()["recovery_code"]
    messy = code.replace("-", "").lower()
    r = client.post("/api/auth/reset-password", json={"recovery_code": messy, "new_password": "newpassword1"})
    assert r.status_code == 200


def test_reset_password_no_account_no_code(client):
    r = client.post("/api/auth/reset-password", json={"recovery_code": "AAAA-AAAA-AAAA", "new_password": "newpassword1"})
    assert r.status_code == 400


def test_recovery_code_settings_endpoints(client):
    reg = client.post("/api/auth/register", json={"username": "olive", "password": "hunter2hunter2"})
    token = reg.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    status = client.get("/api/settings/security/recovery-code", headers=headers)
    assert status.status_code == 200
    assert status.json()["configured"] is True

    rotate = client.post("/api/settings/security/recovery-code", headers=headers)
    assert rotate.status_code == 200
    new_code = rotate.json()["recovery_code"]
    assert new_code

    # The rotated code is what now works for a reset (old one from register no longer does).
    r = client.post("/api/auth/reset-password", json={"recovery_code": reg.json()["recovery_code"], "new_password": "x2y2z2a2"})
    assert r.status_code == 401
    r2 = client.post("/api/auth/reset-password", json={"recovery_code": new_code, "new_password": "x2y2z2a2"})
    assert r2.status_code == 200
