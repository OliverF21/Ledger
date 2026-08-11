from __future__ import annotations

import os
from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import AppConfig, Base  # noqa: E402
from app.risk_free_rate import (  # noqa: E402
    DEFAULT_RISK_FREE_RATE_PCT,
    fetch_and_cache_risk_free_rate,
    get_cached_risk_free_rate,
    parse_fred_csv,
)


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rfr.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


SAMPLE_CSV = "DATE,DGS3MO\n2026-08-04,5.21\n2026-08-05,.\n2026-08-06,5.23\n"


def test_parse_fred_csv_ignores_missing_values():
    assert parse_fred_csv(SAMPLE_CSV) == 5.23


def test_parse_fred_csv_empty_returns_none():
    assert parse_fred_csv("DATE,DGS3MO\n") is None


def test_get_cached_risk_free_rate_defaults_when_unset(db_session):
    assert get_cached_risk_free_rate(db_session) == DEFAULT_RISK_FREE_RATE_PCT


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_fetch_and_cache_risk_free_rate_stores_and_returns_value(db_session, monkeypatch):
    import app.risk_free_rate as rfr_module

    monkeypatch.setattr(rfr_module.requests, "get", lambda url, timeout: _FakeResponse(SAMPLE_CSV))

    rate = fetch_and_cache_risk_free_rate(db_session)
    assert rate == 5.23
    assert get_cached_risk_free_rate(db_session) == 5.23


def test_fetch_and_cache_risk_free_rate_falls_back_on_network_error(db_session, monkeypatch):
    import app.risk_free_rate as rfr_module

    def _raise(url, timeout):
        raise ConnectionError("no network")

    monkeypatch.setattr(rfr_module.requests, "get", _raise)

    rate = fetch_and_cache_risk_free_rate(db_session)
    assert rate == DEFAULT_RISK_FREE_RATE_PCT
