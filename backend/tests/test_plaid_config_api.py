# backend/tests/test_plaid_config_api.py  (part 1: resolver + is_configured)
from __future__ import annotations

import os
from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.pop("PLAID_CLIENT_ID", None)
os.environ.pop("PLAID_SANDBOX_SECRET", None)

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Base  # noqa: E402
from app import app_config, database  # noqa: E402
from app.plaid_service import PlaidService  # noqa: E402


@pytest.fixture()
def memdb(tmp_path, monkeypatch):
    # File-based (not :memory:) so PlaidService._setting()'s independent
    # SessionLocal sees the same DB as the test session — per-connection
    # :memory: DBs would each be empty. Matches tests/test_proposals.py.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ledger.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "SessionLocal", TestSession)
    yield TestSession


def test_appconfig_beats_env(memdb, monkeypatch):
    monkeypatch.setenv("PLAID_CLIENT_ID", "env_cid")
    s = memdb()
    app_config.set(s, app_config.PLAID_CLIENT_ID, "db_cid")
    s.close()
    assert PlaidService._setting("PLAID_CLIENT_ID") == "db_cid"


def test_env_fallback(memdb, monkeypatch):
    monkeypatch.setenv("PLAID_CLIENT_ID", "env_cid")
    assert PlaidService._setting("PLAID_CLIENT_ID") == "env_cid"


def test_is_configured_false_when_empty(memdb, monkeypatch):
    monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
    assert PlaidService.is_configured() is False


def test_validate_config_never_raises(memdb, monkeypatch):
    monkeypatch.setenv("PLAID_ENV", "production")
    monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
    PlaidService.validate_config()  # must not raise


# ── endpoint tests ────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(memdb, monkeypatch):
    # Route get_db to the in-memory session; disable auth dependency.
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


def test_get_plaid_config_empty(client, monkeypatch):
    # The module-level env pop (see top of file) only runs once at import
    # time; app.database's load_dotenv() (triggered by that same import,
    # since it wasn't yet set) can silently repopulate these from a real
    # backend/.env on machines that have one. Clear them again here so this
    # test verifies "nothing configured anywhere" rather than depending on
    # import order / the absence of a local .env.
    monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
    monkeypatch.delenv("PLAID_SANDBOX_SECRET", raising=False)
    monkeypatch.delenv("PLAID_PROD_SECRET", raising=False)
    r = client.get("/api/settings/plaid-config")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["has_secret"] is False
    assert "secret" not in body


def test_configured_true_from_env_only(client, monkeypatch):
    """Env-only creds (app_config empty) must still report configured=True,
    matching PlaidService.is_configured()'s fallback so a dev user
    with .env Plaid creds doesn't get routed into the setup wizard."""
    monkeypatch.setenv("PLAID_CLIENT_ID", "envcid")
    monkeypatch.setenv("PLAID_SANDBOX_SECRET", "envsec")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    r = client.get("/api/settings/plaid-config")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["has_secret"] is False  # app_config table itself is empty


def test_put_then_get_hides_secret(client):
    r = client.put("/api/settings/plaid-config", json={
        "client_id": "cid", "env": "sandbox", "secret": "sec"})
    assert r.status_code == 200
    assert r.json()["has_secret"] is True
    assert "secret" not in r.json()
    g = client.get("/api/settings/plaid-config").json()
    assert g["client_id"] == "cid"
    assert g["has_secret"] is True
    assert g["configured"] is True


def test_put_without_secret_keeps_existing(client):
    client.put("/api/settings/plaid-config", json={"client_id": "cid", "env": "sandbox", "secret": "sec"})
    client.put("/api/settings/plaid-config", json={"client_id": "cid2", "env": "sandbox"})
    g = client.get("/api/settings/plaid-config").json()
    assert g["client_id"] == "cid2"
    assert g["has_secret"] is True  # secret preserved


def test_test_connection_ok(client, monkeypatch):
    monkeypatch.setattr("app.plaid_service.PlaidService.create_link_token",
                        staticmethod(lambda *a, **k: ("link-sandbox-token", False)))
    r = client.post("/api/settings/plaid-config/test", json={
        "client_id": "cid", "env": "sandbox", "secret": "sec"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_test_connection_bad_key(client, monkeypatch):
    def _boom(*a, **k):
        raise Exception("INVALID_API_KEYS: client_id/secret invalid")
    monkeypatch.setattr("app.plaid_service.PlaidService.create_link_token", staticmethod(_boom))
    distinctive_secret = "zzsecretvalue123"
    r = client.post("/api/settings/plaid-config/test", json={
        "client_id": "cid", "env": "sandbox", "secret": distinctive_secret})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert distinctive_secret not in r.json()["message"]  # secret never echoed
