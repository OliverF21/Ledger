# backend/tests/test_advisor_config.py
from __future__ import annotations

import os
from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.pop("PROPOSAL_SERVICE_KEY", None)

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Base  # noqa: E402
from app import database  # noqa: E402


@pytest.fixture()
def memdb(tmp_path, monkeypatch):
    # File-based (not :memory:) so app.auth._proposal_service_key()'s
    # independent SessionLocal sees the same DB as the test session — matches
    # tests/test_plaid_config_api.py.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ledger.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "SessionLocal", TestSession)
    yield TestSession


@pytest.fixture()
def client(memdb, monkeypatch):
    monkeypatch.delenv("PROPOSAL_SERVICE_KEY", raising=False)
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


def test_get_advisor_config_not_configured_initially(client, monkeypatch):
    # The module-level env pop (see top of file) only runs once at import
    # time; app.database's load_dotenv() (triggered by that same import,
    # since it wasn't yet set) can silently repopulate this from a real
    # backend/.env on machines that have one. Clear it again here so this
    # test verifies "nothing configured anywhere" rather than depending on
    # import order / the absence of a local .env. Matches
    # tests/test_plaid_config_api.py::test_get_plaid_config_empty.
    monkeypatch.delenv("PROPOSAL_SERVICE_KEY", raising=False)
    r = client.get("/api/settings/advisor-config")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["service_key"] is None
    assert body["config_snippet"] == ""


def test_generate_then_get_returns_same_key(client):
    r = client.post("/api/settings/advisor-config/generate")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["service_key"]
    assert len(body["service_key"]) > 10
    assert body["service_key"] in body["config_snippet"]

    g = client.get("/api/settings/advisor-config")
    assert g.status_code == 200
    g_body = g.json()
    assert g_body["configured"] is True
    assert g_body["service_key"] == body["service_key"]
    assert g_body["config_snippet"] == body["config_snippet"]


def test_generate_twice_rotates_key(client):
    r1 = client.post("/api/settings/advisor-config/generate").json()
    r2 = client.post("/api/settings/advisor-config/generate").json()
    assert r1["service_key"] != r2["service_key"]
    g = client.get("/api/settings/advisor-config").json()
    assert g["service_key"] == r2["service_key"]
