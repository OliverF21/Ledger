"""Tests for GET/PUT /api/settings/sync-config (persisted sync frequency)."""
from __future__ import annotations

import os
from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Base  # noqa: E402
from app import database  # noqa: E402


@pytest.fixture()
def memdb(tmp_path, monkeypatch):
    # File-based (not :memory:) so any code using its own SessionLocal (e.g.
    # scheduler.reschedule_sync -> app_config lookups) sees the same DB.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ledger.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "SessionLocal", TestSession)
    yield TestSession


from fastapi.testclient import TestClient  # noqa: E402


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


def test_get_sync_config_default(client):
    r = client.get("/api/settings/sync-config")
    assert r.status_code == 200
    assert r.json() == {"frequency_hours": 6}


def test_put_valid_sync_config(client):
    r = client.put("/api/settings/sync-config", json={"frequency_hours": 12})
    assert r.status_code == 200
    assert r.json() == {"frequency_hours": 12}

    g = client.get("/api/settings/sync-config")
    assert g.json() == {"frequency_hours": 12}


def test_put_manual_sync_config(client):
    r = client.put("/api/settings/sync-config", json={"frequency_hours": 0})
    assert r.status_code == 200
    assert r.json() == {"frequency_hours": 0}


def test_put_invalid_sync_config_rejected(client):
    r = client.put("/api/settings/sync-config", json={"frequency_hours": 3})
    assert r.status_code == 400

    # Unchanged from default since the invalid update was rejected.
    g = client.get("/api/settings/sync-config")
    assert g.json() == {"frequency_hours": 6}
