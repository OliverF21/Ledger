from __future__ import annotations

import os
from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Base  # noqa: E402


@pytest.fixture()
def memdb(tmp_path, monkeypatch):
    from app import database

    engine = create_engine(
        f"sqlite:///{tmp_path / 'ledger.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "SessionLocal", TestSession)
    yield TestSession


@pytest.fixture()
def client(memdb):
    import main
    from app import database
    from app.auth import require_auth
    from fastapi.testclient import TestClient

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


def test_get_risk_metrics_with_no_data_returns_nulls(client):
    resp = client.get("/api/investments/risk/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["volatility_pct"] is None
    assert body["data_points"] == 0
    assert body["lookback_days"] == 365


def test_get_risk_metrics_respects_lookback_days_param(client):
    resp = client.get("/api/investments/risk/metrics?lookback_days=90")
    assert resp.status_code == 200
    assert resp.json()["lookback_days"] == 90


def test_get_risk_metrics_rejects_out_of_range_lookback(client):
    resp = client.get("/api/investments/risk/metrics?lookback_days=5")
    assert resp.status_code == 422
