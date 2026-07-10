# backend/tests/test_weekly_email_config.py
"""BYOK weekly-email transport config: /api/settings/weekly-email.

Mirrors the fixture pattern in tests/test_plaid_config_api.py: a file-based
SQLite DB (so PlaidService/email_sender's independent SessionLocal sees the
same rows as the test session) with require_auth + get_db overridden.
"""
from __future__ import annotations

import os
from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.pop("RESEND_API_KEY", None)
os.environ.pop("WEEKLY_EMAIL_FROM", None)

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

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
    s = TestSession()
    s.add(User(id=1, username="default_user"))
    s.commit()
    s.close()
    yield TestSession


@pytest.fixture()
def client(memdb, monkeypatch):
    import main
    from app import database
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


from fastapi.testclient import TestClient  # noqa: E402


def test_get_shows_no_resend_key_initially(client, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    r = client.get("/api/settings/weekly-email")
    assert r.status_code == 200
    body = r.json()
    assert body["has_resend_key"] is False
    assert body["transport_configured"] is False
    assert "resend_api_key" not in body


def test_put_key_then_get_shows_configured_and_hides_key(client, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    r = client.put("/api/settings/weekly-email", json={"resend_api_key": "re_secret_123"})
    assert r.status_code == 200
    body = r.json()
    assert body["has_resend_key"] is True
    assert body["transport_configured"] is True
    assert "resend_api_key" not in body
    assert "re_secret_123" not in r.text

    g = client.get("/api/settings/weekly-email").json()
    assert g["has_resend_key"] is True
    assert "re_secret_123" not in client.get("/api/settings/weekly-email").text


def test_blank_key_on_later_put_keeps_stored_key(client, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    client.put("/api/settings/weekly-email", json={"resend_api_key": "re_secret_123"})
    # A later PUT with no key (or blank) must not clear the stored one.
    r = client.put("/api/settings/weekly-email", json={"email": "me@example.com"})
    assert r.status_code == 200
    assert r.json()["has_resend_key"] is True

    r2 = client.put("/api/settings/weekly-email", json={"resend_api_key": ""})
    assert r2.status_code == 200
    assert r2.json()["has_resend_key"] is True


def test_from_address_roundtrip(client, monkeypatch):
    monkeypatch.delenv("WEEKLY_EMAIL_FROM", raising=False)
    r = client.put("/api/settings/weekly-email", json={"from_address": "Ledger <me@mydomain.com>"})
    assert r.status_code == 200
    assert r.json()["from_address"] == "Ledger <me@mydomain.com>"


def test_env_fallback_reports_configured_without_app_config(client, monkeypatch):
    """A dev user with RESEND_API_KEY only in .env should still see
    transport_configured=True, matching email_sender.is_configured()."""
    monkeypatch.setenv("RESEND_API_KEY", "env_key")
    r = client.get("/api/settings/weekly-email")
    body = r.json()
    assert body["transport_configured"] is True
    assert body["has_resend_key"] is True
